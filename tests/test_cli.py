import logging
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import openai
import pytest
from agents import Runner, set_tracing_disabled
from agents import _debug as agents_debug
from agents.exceptions import MaxTurnsExceeded
from agents.models import _openai_shared
from agents.models.openai_responses import OpenAIResponsesModel
from agents.tracing import get_trace_provider
from agents.tracing.traces import NoOpTrace

from conftest import FAKE_API_KEY, REAL_RUN_SYNC
from maos import cli
from maos.agents.research_agent import EmptyResearchOutputError

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


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


# SDK logging. These run the real CLI and the real Runner; only the HTTP call
# inside the SDK's Responses model is replaced, so the SDK's own error
# logging path runs exactly as it would after a real 401.

AUTH_ERROR_LINE = "Error: OpenAI rejected the API key. Check OPENAI_API_KEY.\n"


class _RecordingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


async def _fetch_response_rejects_key(self, *args, **kwargs):
    raise openai.AuthenticationError(
        f"Incorrect API key provided: {FAKE_API_KEY}",
        response=_response(401), body=None,
    )


@pytest.mark.parametrize("dont_log_model_data", [True, False], ids=["redacted", "verbose"])
def test_sdk_auth_error_log_does_not_reach_output(
    monkeypatch, capsys, caplog, dont_log_model_data
):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    monkeypatch.setattr(_openai_shared, "_default_openai_key", None)
    monkeypatch.setattr(agents_debug, "DONT_LOG_MODEL_DATA", dont_log_model_data)
    monkeypatch.setattr(Runner, "run_sync", REAL_RUN_SYNC)
    monkeypatch.setattr(OpenAIResponsesModel, "_fetch_response", _fetch_response_rejects_key)

    # Attached directly to the SDK logger, so it proves the SDK did log.
    recorder = _RecordingHandler()
    sdk_logger = logging.getLogger("openai.agents")
    sdk_logger.addHandler(recorder)
    caplog.set_level(logging.DEBUG)

    assert cli.main(["Outlook"]) == cli.EXIT_RUN_ERROR

    assert any(r.getMessage().startswith("Error getting response") for r in recorder.records)
    if not dont_log_model_data:
        assert any(FAKE_API_KEY in r.getMessage() for r in recorder.records)

    out, err = _assert_key_not_leaked(capsys)
    assert out == ""
    assert err == AUTH_ERROR_LINE
    assert not [r for r in caplog.records if r.name.startswith("openai")]


def test_silence_sdk_logging_is_idempotent():
    cli.silence_sdk_logging()
    cli.silence_sdk_logging()
    for name in cli.SDK_LOGGERS:
        logger = logging.getLogger(name)
        assert logger.propagate is False
        assert sum(isinstance(h, logging.NullHandler) for h in logger.handlers) == 1


_SUBPROCESS_SCRIPT = """
import socket, sys
from types import SimpleNamespace

def _blocked(*args, **kwargs):
    raise RuntimeError("network access blocked")

socket.socket.connect = socket.socket.connect_ex = _blocked
socket.create_connection = socket.getaddrinfo = _blocked

sys.path.insert(0, sys.argv[1])
import openai
from agents.models.openai_responses import OpenAIResponsesModel
from maos import cli

async def _fetch_response(self, *args, **kwargs):
    raise openai.AuthenticationError(
        "Incorrect API key provided: " + sys.argv[2],
        response=SimpleNamespace(request=None, status_code=401, headers={}),
        body=None,
    )

OpenAIResponsesModel._fetch_response = _fetch_response
if sys.argv[3] == "unsilenced":
    cli.silence_sdk_logging = lambda: None
sys.exit(cli.main(["Outlook"]))
"""


def _run_cli_subprocess(tmp_path, mode):
    """Run the CLI in a fresh interpreter with no logging configured.

    pytest installs root log handlers, which hide Python's last-resort stderr
    handler in-process; a subprocess reproduces what a user's terminal sees.
    """
    env = {
        k: v for k, v in os.environ.items()
        if not k.startswith(("OPENAI_", "MAOS_"))
    }
    env["OPENAI_API_KEY"] = FAKE_API_KEY
    env["OPENAI_AGENTS_DONT_LOG_MODEL_DATA"] = "0"
    return subprocess.run(
        [sys.executable, "-I", "-c", _SUBPROCESS_SCRIPT, str(SRC_DIR), FAKE_API_KEY, mode],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60,
    )


def test_subprocess_auth_error_does_not_leak_key_to_stderr(tmp_path):
    result = _run_cli_subprocess(tmp_path, "silenced")
    assert result.returncode == cli.EXIT_RUN_ERROR
    assert result.stdout == ""
    assert result.stderr == AUTH_ERROR_LINE
    assert FAKE_API_KEY not in result.stdout + result.stderr


def test_subprocess_control_shows_leak_without_silencing(tmp_path):
    """Control: proves the subprocess test can detect the SDK log leak."""
    result = _run_cli_subprocess(tmp_path, "unsilenced")
    assert result.returncode == cli.EXIT_RUN_ERROR
    assert "Error getting response" in result.stderr
    assert FAKE_API_KEY in result.stderr


# Optional CLI fields, through the real run_research() with the SDK run faked.

def test_whitespace_only_optional_fields_are_omitted_end_to_end(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    monkeypatch.setattr(cli, "set_default_openai_key", lambda *a, **k: None)
    seen = {}

    def fake_run_sync(agent, input, **kwargs):
        seen["input"] = input
        return SimpleNamespace(final_output="## Research Request\nok")

    monkeypatch.setattr(Runner, "run_sync", fake_run_sync)

    code = cli.main(
        ["Outlook", "--subject", "  ", "--topic", "\t", "--period", " FY2025 "]
    )

    assert code == cli.EXIT_OK
    assert seen["input"] == "Research request: Outlook\nRelevant time period: FY2025"
    _assert_key_not_leaked(capsys)
