from types import SimpleNamespace

import openai
import pytest
from agents import Runner, set_tracing_disabled
from agents.exceptions import MaxTurnsExceeded
from agents.tracing import get_trace_provider
from agents.tracing.traces import NoOpTrace

from conftest import FAKE_API_KEY
from maos import cli
from maos.agents.research_agent import EmptyResearchOutputError


@pytest.fixture
def spies(monkeypatch):
    """Record the SDK key setter and fake the research run."""
    recorded = {"key_calls": [], "run": None}

    monkeypatch.setattr(
        cli, "set_default_openai_key",
        lambda key, use_for_tracing=True: recorded["key_calls"].append(
            (key, use_for_tracing)
        ),
    )

    def fake_run_research(request, **kwargs):
        recorded["run"] = (request, kwargs)
        return "## Research Request\nMocked output"

    monkeypatch.setattr(cli, "run_research", fake_run_research)
    return recorded


def _assert_key_not_leaked(capsys):
    out, err = capsys.readouterr()
    assert FAKE_API_KEY not in out
    assert FAKE_API_KEY not in err
    return out, err


def test_missing_key_exits_with_config_error(spies, capsys):
    assert cli.main(["Outlook"]) == cli.EXIT_CONFIG_ERROR
    _, err = capsys.readouterr()
    assert "OPENAI_API_KEY is not set" in err
    assert spies["run"] is None


def test_empty_request_is_rejected(spies):
    with pytest.raises(SystemExit) as exc:
        cli.main(["   "])
    assert exc.value.code == 2


def test_successful_run_prints_markdown(monkeypatch, spies, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("MAOS_RESEARCH_MODEL", "my-model")

    code = cli.main(
        ["Outlook", "--subject", "ACME", "--topic", "margins", "--period", "FY2025"]
    )

    assert code == cli.EXIT_OK
    out, _ = _assert_key_not_leaked(capsys)
    assert "## Research Request" in out
    assert spies["run"] == (
        "Outlook",
        {"subject": "ACME", "topic": "margins", "period": "FY2025", "model": "my-model"},
    )


def test_api_key_is_not_used_for_tracing(monkeypatch, spies):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    cli.main(["Outlook"])
    assert spies["key_calls"] == [(FAKE_API_KEY, False)]


def test_cli_run_disables_tracing_before_sdk_run(monkeypatch, capsys):
    """End to end through the real run_research(), with only the SDK run faked."""
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    monkeypatch.setattr(cli, "set_default_openai_key", lambda *a, **k: None)
    set_tracing_disabled(False)
    observed = {}

    def fake_run_sync(agent, input, **kwargs):
        observed["trace"] = get_trace_provider().create_trace("check")
        observed["run_config"] = kwargs.get("run_config")
        return SimpleNamespace(final_output="## Research Request\nok")

    monkeypatch.setattr(Runner, "run_sync", fake_run_sync)

    assert cli.main(["Outlook"]) == cli.EXIT_OK
    assert isinstance(observed["trace"], NoOpTrace)
    assert observed["run_config"].tracing_disabled is True
    _assert_key_not_leaked(capsys)


def _response(status_code):
    """Minimal stand-in for an HTTP response, sufficient for openai errors."""
    return SimpleNamespace(request=None, status_code=status_code, headers={})


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            openai.AuthenticationError(
                f"Incorrect API key provided: {FAKE_API_KEY}",
                response=_response(401), body=None,
            ),
            "OpenAI rejected the API key",
        ),
        (
            openai.RateLimitError("rate limited", response=_response(429), body=None),
            "rate limit",
        ),
        (openai.APIConnectionError(request=None), "could not connect"),
        (
            openai.NotFoundError(
                "The model `bad-model` does not exist", response=_response(404), body=None
            ),
            "HTTP 404",
        ),
        (
            openai.BadRequestError(
                "Invalid model: bad-model", response=_response(400), body=None
            ),
            "HTTP 400",
        ),
        (
            openai.InternalServerError("server error", response=_response(500), body=None),
            "HTTP 500",
        ),
        (openai.OpenAIError(f"generic failure {FAKE_API_KEY}"), "OpenAI request failed"),
        (MaxTurnsExceeded("too many turns"), "agent run failed"),
        (EmptyResearchOutputError("the agent returned no output"), "returned no output"),
        (ValueError(f"unexpected {FAKE_API_KEY}"), "unexpected error (ValueError)"),
    ],
    ids=[
        "auth", "rate-limit", "connection", "invalid-model-404", "invalid-model-400",
        "server", "generic-openai", "agents", "empty-output", "unexpected",
    ],
)
def test_run_errors_exit_cleanly_without_leaking_key(
    monkeypatch, spies, capsys, error, message
):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)

    def failing_run(*args, **kwargs):
        raise error

    monkeypatch.setattr(cli, "run_research", failing_run)

    assert cli.main(["Outlook"]) == cli.EXIT_RUN_ERROR
    out, err = _assert_key_not_leaked(capsys)
    assert out == ""
    assert err.startswith("Error: ")
    assert message in err
    assert "Traceback" not in err


@pytest.mark.parametrize("final_output", [None, ""], ids=["none", "empty"])
def test_empty_model_output_exits_with_error(monkeypatch, capsys, final_output):
    """Through the real run_research(), with only the SDK run faked."""
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    monkeypatch.setattr(cli, "set_default_openai_key", lambda *a, **k: None)
    monkeypatch.setattr(
        Runner, "run_sync",
        lambda agent, input, **kwargs: SimpleNamespace(final_output=final_output),
    )

    assert cli.main(["Outlook"]) == cli.EXIT_RUN_ERROR
    out, err = capsys.readouterr()
    assert out == ""
    assert err == "Error: the agent returned no output.\n"


def test_keyboard_interrupt(monkeypatch, spies, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_research", interrupted)
    assert cli.main(["Outlook"]) == cli.EXIT_INTERRUPTED
