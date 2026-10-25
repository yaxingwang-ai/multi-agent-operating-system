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
from maos import __version__, workflow_cli
from maos.agents import investment_analyst, research_agent
from maos.contracts import OutputValidationError, WorkflowRequest
from maos.workflow import DISCLAIMER, WorkflowStageError
from mock_agents import ANALYSIS_MARKDOWN, RESEARCH_MARKDOWN

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


def _response(status_code):
    return SimpleNamespace(request=None, status_code=status_code, headers={})


def _stage_error(stage, cause):
    try:
        raise WorkflowStageError(stage) from cause
    except WorkflowStageError as exc:
        return exc


@pytest.fixture
def spies(monkeypatch):
    """Record the SDK key setter and fake the workflow run."""
    recorded = {"key_calls": [], "run": None}
    monkeypatch.setattr(
        workflow_cli, "set_default_openai_key",
        lambda key, use_for_tracing=True: recorded["key_calls"].append(
            (key, use_for_tracing)
        ),
    )

    def fake_run_workflow(request, **kwargs):
        recorded["run"] = (request, kwargs)
        return SimpleNamespace(report_markdown="# Report\n")

    monkeypatch.setattr(workflow_cli, "run_workflow", fake_run_workflow)
    return recorded


def _fake_agents(monkeypatch, outputs=None):
    """Fake the SDK run for both real agents, keyed by agent name."""
    outputs = outputs or {
        research_agent.AGENT_NAME: RESEARCH_MARKDOWN,
        investment_analyst.AGENT_NAME: ANALYSIS_MARKDOWN,
    }
    seen = []

    def fake_run_sync(agent, input, **kwargs):
        seen.append({
            "agent": agent.name,
            "model": agent.model,
            "trace": get_trace_provider().create_trace("check"),
            "run_config": kwargs.get("run_config"),
        })
        output = outputs[agent.name]
        if isinstance(output, BaseException):
            raise output
        return SimpleNamespace(final_output=output)

    monkeypatch.setattr(workflow_cli, "set_default_openai_key", lambda *a, **k: None)
    monkeypatch.setattr(Runner, "run_sync", fake_run_sync)
    return seen


def _assert_key_not_leaked(capsys):
    out, err = capsys.readouterr()
    assert FAKE_API_KEY not in out
    assert FAKE_API_KEY not in err
    return out, err


def test_missing_key_exits_with_config_error(spies, capsys):
    assert workflow_cli.main(["Outlook"]) == workflow_cli.EXIT_CONFIG_ERROR
    _, err = capsys.readouterr()
    assert "OPENAI_API_KEY is not set" in err
    assert spies["run"] is None


def test_empty_request_is_rejected(spies):
    with pytest.raises(SystemExit) as exc:
        workflow_cli.main(["   "])
    assert exc.value.code == 2


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        workflow_cli.main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out == f"maos-workflow {__version__}\n"


def test_successful_run_passes_request_and_shared_model(monkeypatch, spies, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("MAOS_RESEARCH_MODEL", "my-model")

    code = workflow_cli.main(
        ["Outlook", "--subject", "ACME", "--topic", "margins", "--period", "FY2025"]
    )

    assert code == workflow_cli.EXIT_OK
    out, _ = _assert_key_not_leaked(capsys)
    assert out == "# Report\n"
    assert spies["run"] == (
        WorkflowRequest("Outlook", subject="ACME", topic="margins", period="FY2025"),
        {"model": "my-model"},
    )
    assert spies["key_calls"] == [(FAKE_API_KEY, False)]


def test_end_to_end_with_faked_sdk_run(monkeypatch, capsys):
    """Through the real workflow and both real agents; only the SDK run is faked."""
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("MAOS_RESEARCH_MODEL", "my-model")
    set_tracing_disabled(False)
    seen = _fake_agents(monkeypatch)

    assert workflow_cli.main(["Outlook"]) == workflow_cli.EXIT_OK

    out, err = _assert_key_not_leaked(capsys)
    assert err == ""
    assert out.startswith("# MAOS Investment Research Report")
    assert DISCLAIMER in out
    assert [(s["agent"], s["model"]) for s in seen] == [
        (research_agent.AGENT_NAME, "my-model"),
        (investment_analyst.AGENT_NAME, "my-model"),
    ]
    for call in seen:
        assert isinstance(call["trace"], NoOpTrace)
        assert call["run_config"].tracing_disabled is True


@pytest.mark.parametrize(
    ("outputs", "expected_err", "agents_run"),
    [
        (
            {research_agent.AGENT_NAME: ""},
            "Error: research stage: the agent returned no output.\n",
            1,
        ),
        (
            {research_agent.AGENT_NAME: "## Research Request\nonly one section"},
            "Error: research stage: the agent's output was invalid (",
            1,
        ),
        (
            {
                research_agent.AGENT_NAME: RESEARCH_MARKDOWN,
                investment_analyst.AGENT_NAME: None,
            },
            "Error: analyst stage: the agent returned no output.\n",
            2,
        ),
        (
            {
                research_agent.AGENT_NAME: RESEARCH_MARKDOWN,
                investment_analyst.AGENT_NAME: ANALYSIS_MARKDOWN.replace("## Risks", "## Threats"),
            },
            "Error: analyst stage: the agent's output was invalid "
            "(unexpected section: 'Threats'; missing section: Risks).\n",
            2,
        ),
    ],
    ids=["research-empty", "research-invalid", "analyst-empty", "analyst-invalid"],
)
def test_stage_output_failures_end_to_end(monkeypatch, capsys, outputs, expected_err, agents_run):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    seen = _fake_agents(monkeypatch, outputs)

    assert workflow_cli.main(["Outlook"]) == workflow_cli.EXIT_RUN_ERROR

    out, err = _assert_key_not_leaked(capsys)
    assert out == ""
    assert err.startswith(expected_err)
    assert len(seen) == agents_run


@pytest.mark.parametrize(
    ("cause", "message"),
    [
        (
            openai.AuthenticationError(
                f"Incorrect API key provided: {FAKE_API_KEY}",
                response=_response(401), body=None,
            ),
            "OpenAI rejected the API key",
        ),
        (openai.RateLimitError("rate limited", response=_response(429), body=None), "rate limit"),
        (openai.APIConnectionError(request=None), "could not connect"),
        (
            openai.NotFoundError(
                f"model not found {FAKE_API_KEY}", response=_response(404), body=None
            ),
            "HTTP 404",
        ),
        (openai.OpenAIError(f"generic failure {FAKE_API_KEY}"), "OpenAI request failed"),
        (MaxTurnsExceeded(f"too many turns {FAKE_API_KEY}"), "agent run failed"),
        (ValueError(f"unexpected {FAKE_API_KEY}"), "unexpected error (ValueError)"),
    ],
    ids=["auth", "rate-limit", "connection", "404", "generic-openai", "agents", "unexpected"],
)
@pytest.mark.parametrize("stage", ["research", "analyst"])
def test_stage_errors_exit_cleanly_without_leaking_key(
    monkeypatch, spies, capsys, stage, cause, message
):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)

    def failing_run(*args, **kwargs):
        raise _stage_error(stage, cause)

    monkeypatch.setattr(workflow_cli, "run_workflow", failing_run)

    assert workflow_cli.main(["Outlook"]) == workflow_cli.EXIT_RUN_ERROR
    out, err = _assert_key_not_leaked(capsys)
    assert out == ""
    assert err.startswith(f"Error: {stage} stage: ")
    assert message in err
    assert "Traceback" not in err
    assert err.count("\n") == 1


def test_validation_problems_are_listed(monkeypatch, spies, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    cause = OutputValidationError(["missing section: Risks", "empty section: Assumptions"])

    def failing_run(*args, **kwargs):
        raise _stage_error("analyst", cause)

    monkeypatch.setattr(workflow_cli, "run_workflow", failing_run)

    assert workflow_cli.main(["Outlook"]) == workflow_cli.EXIT_RUN_ERROR
    assert capsys.readouterr().err == (
        "Error: analyst stage: the agent's output was invalid "
        "(missing section: Risks; empty section: Assumptions).\n"
    )


def test_validation_message_is_bounded_end_to_end(monkeypatch, capsys):
    """Real workflow; the research agent returns 100 unexpected sections."""
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    junk = "\n".join(f"## Junk {i}\nz" for i in range(100))
    _fake_agents(monkeypatch, {research_agent.AGENT_NAME: junk + "\n" + RESEARCH_MARKDOWN})

    assert workflow_cli.main(["Outlook"]) == workflow_cli.EXIT_RUN_ERROR

    out, err = _assert_key_not_leaked(capsys)
    assert out == ""
    assert err == (
        "Error: research stage: the agent's output was invalid ("
        + "; ".join(f"unexpected section: 'Junk {i}'" for i in range(5))
        + "; and 95 more problems).\n"
    )


def test_unexpected_error_outside_stages(monkeypatch, spies, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)

    def failing_run(*args, **kwargs):
        raise RuntimeError(f"boom {FAKE_API_KEY}")

    monkeypatch.setattr(workflow_cli, "run_workflow", failing_run)

    assert workflow_cli.main(["Outlook"]) == workflow_cli.EXIT_RUN_ERROR
    out, err = _assert_key_not_leaked(capsys)
    assert err == "Error: unexpected error (RuntimeError).\n"


def test_keyboard_interrupt(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    _fake_agents(monkeypatch, {research_agent.AGENT_NAME: KeyboardInterrupt()})

    assert workflow_cli.main(["Outlook"]) == workflow_cli.EXIT_INTERRUPTED
    assert capsys.readouterr().err == "Error: interrupted.\n"


def test_keyboard_interrupt_during_analyst_stage(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    seen = _fake_agents(monkeypatch, {
        research_agent.AGENT_NAME: RESEARCH_MARKDOWN,
        investment_analyst.AGENT_NAME: KeyboardInterrupt(),
    })

    assert workflow_cli.main(["Outlook"]) == workflow_cli.EXIT_INTERRUPTED
    assert [s["agent"] for s in seen] == [
        research_agent.AGENT_NAME, investment_analyst.AGENT_NAME,
    ]
    assert capsys.readouterr() == ("", "Error: interrupted.\n")


# SDK logging. These run the real CLI, workflow and Runner; only the HTTP call
# inside the SDK's Responses model is replaced. For the analyst stage, the
# research agent is replaced so the analyst is the agent that hits the API.

STAGE_AUTH_ERROR_LINE = "Error: {} stage: OpenAI rejected the API key. Check OPENAI_API_KEY.\n"


class _RecordingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.mark.parametrize("dont_log_model_data", [True, False], ids=["redacted", "verbose"])
@pytest.mark.parametrize("stage", ["research", "analyst"])
def test_sdk_auth_error_log_does_not_reach_output(
    monkeypatch, capsys, caplog, stage, dont_log_model_data
):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    monkeypatch.setattr(_openai_shared, "_default_openai_key", None)
    monkeypatch.setattr(agents_debug, "DONT_LOG_MODEL_DATA", dont_log_model_data)
    monkeypatch.setattr(Runner, "run_sync", REAL_RUN_SYNC)
    if stage == "analyst":
        monkeypatch.setattr(
            research_agent, "run_research", lambda *a, **k: RESEARCH_MARKDOWN
        )
    fetched = []

    async def fetch_response_rejects_key(self, system_instructions, *args, **kwargs):
        fetched.append(system_instructions)
        raise openai.AuthenticationError(
            f"Incorrect API key provided: {FAKE_API_KEY}",
            response=_response(401), body=None,
        )

    monkeypatch.setattr(OpenAIResponsesModel, "_fetch_response", fetch_response_rejects_key)

    # Attached directly to the SDK logger, so it proves the SDK did log.
    recorder = _RecordingHandler()
    logging.getLogger("openai.agents").addHandler(recorder)
    caplog.set_level(logging.DEBUG)

    assert workflow_cli.main(["Outlook"]) == workflow_cli.EXIT_RUN_ERROR

    expected_instructions = {
        "research": research_agent.RESEARCH_AGENT_INSTRUCTIONS,
        "analyst": investment_analyst.INVESTMENT_ANALYST_INSTRUCTIONS,
    }[stage]
    assert fetched and set(fetched) == {expected_instructions}
    assert any(r.getMessage().startswith("Error getting response") for r in recorder.records)
    if not dont_log_model_data:
        assert any(FAKE_API_KEY in r.getMessage() for r in recorder.records)

    out, err = _assert_key_not_leaked(capsys)
    assert out == ""
    assert err == STAGE_AUTH_ERROR_LINE.format(stage)
    assert not [r for r in caplog.records if r.name.startswith("openai")]


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
from maos import workflow_cli
from maos.agents import research_agent

async def _fetch_response(self, *args, **kwargs):
    raise openai.AuthenticationError(
        "Incorrect API key provided: " + sys.argv[2],
        response=SimpleNamespace(request=None, status_code=401, headers={}),
        body=None,
    )

OpenAIResponsesModel._fetch_response = _fetch_response
if sys.argv[3] == "analyst":
    research = "\\n\\n".join(
        f"## {name}\\n{name} body." for name in research_agent.OUTPUT_SECTIONS
    )
    research_agent.run_research = lambda *args, **kwargs: research
if sys.argv[4] == "unsilenced":
    workflow_cli.silence_sdk_logging = lambda: None
sys.exit(workflow_cli.main(["Outlook"]))
"""


def _run_workflow_subprocess(tmp_path, stage, mode):
    """Run maos-workflow in a fresh interpreter with no logging configured.

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
        [sys.executable, "-I", "-c", _SUBPROCESS_SCRIPT, str(SRC_DIR), FAKE_API_KEY,
         stage, mode],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60,
    )


@pytest.mark.parametrize("stage", ["research", "analyst"])
def test_subprocess_auth_error_does_not_leak_key_to_stderr(tmp_path, stage):
    result = _run_workflow_subprocess(tmp_path, stage, "silenced")
    assert result.returncode == workflow_cli.EXIT_RUN_ERROR
    assert result.stdout == ""
    assert result.stderr == STAGE_AUTH_ERROR_LINE.format(stage)
    assert FAKE_API_KEY not in result.stdout + result.stderr


def test_subprocess_control_shows_leak_without_silencing(tmp_path):
    """Control: proves the subprocess test can detect the SDK log leak."""
    result = _run_workflow_subprocess(tmp_path, "analyst", "unsilenced")
    assert result.returncode == workflow_cli.EXIT_RUN_ERROR
    assert "Error getting response" in result.stderr
    assert FAKE_API_KEY in result.stderr
