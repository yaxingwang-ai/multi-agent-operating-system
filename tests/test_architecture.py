"""The workflow core must stay reusable by the CLI and a future API layer."""

import subprocess
import sys
from pathlib import Path

import openai
import pytest

from conftest import FAKE_API_KEY
from maos.contracts import OutputValidationError, WorkflowRequest
from maos.errors import describe_run_error, describe_stage_error
from maos.workflow import WorkflowStageError, run_workflow
from mock_agents import ANALYSIS_MARKDOWN, RESEARCH_MARKDOWN, MockAgent

SRC_DIR = Path(__file__).resolve().parents[1] / "src"

CORE_MODULES = ("maos.contracts", "maos.workflow", "maos.errors")
CLI_MODULES = ("maos.cli", "maos.workflow_cli", "argparse")


def test_core_modules_do_not_import_cli_code():
    """Checked in a fresh interpreter, since pytest itself loads argparse."""
    script = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        f"import {', '.join(CORE_MODULES)}; "
        f"print([m for m in {CLI_MODULES!r} if m in sys.modules])"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(SRC_DIR)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_research_cli_does_not_load_the_workflow():
    """maos-research must not depend on V1.2 workflow or analyst code."""
    script = (
        "import sys; sys.path.insert(0, sys.argv[1]); import maos.cli; "
        "print([m for m in ('maos.workflow', 'maos.agents.investment_analyst') "
        "if m in sys.modules])"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(SRC_DIR)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_workflow_prints_nothing_on_success(capsys):
    run_workflow(
        WorkflowRequest("Outlook"),
        research_fn=MockAgent(RESEARCH_MARKDOWN),
        analyst_fn=MockAgent(ANALYSIS_MARKDOWN),
    )
    assert capsys.readouterr() == ("", "")


def test_workflow_prints_nothing_on_failure(capsys):
    with pytest.raises(WorkflowStageError):
        run_workflow(
            WorkflowRequest("Outlook"),
            research_fn=MockAgent(error=RuntimeError("boom")),
            analyst_fn=MockAgent(ANALYSIS_MARKDOWN),
        )
    assert capsys.readouterr() == ("", "")


def _stage_error(stage, cause):
    try:
        raise WorkflowStageError(stage) from cause
    except WorkflowStageError as exc:
        return exc


@pytest.mark.parametrize(
    ("cause", "expected"),
    [
        (openai.APIConnectionError(request=None),
         "research stage: could not connect to the OpenAI API. Check your network."),
        (OutputValidationError(["missing section: Risks"]),
         "research stage: the agent's output was invalid (missing section: Risks)."),
        (RuntimeError(f"secret {FAKE_API_KEY}"),
         "research stage: unexpected error (RuntimeError)."),
    ],
    ids=["api", "validation", "unexpected"],
)
def test_safe_error_descriptions_work_without_a_cli(cause, expected):
    assert describe_stage_error(_stage_error("research", cause)) == expected


def test_describe_run_error_never_includes_exception_text():
    assert FAKE_API_KEY not in describe_run_error(openai.OpenAIError(FAKE_API_KEY))
