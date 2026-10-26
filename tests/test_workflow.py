from types import SimpleNamespace

import openai
import pytest
from agents import Runner

from maos.agents import investment_analyst, research_agent
from maos.contracts import OutputValidationError, ResearchReport, WorkflowRequest
from maos.workflow import (
    DISCLAIMER,
    STAGE_ANALYST,
    STAGE_RESEARCH,
    WorkflowStageError,
    run_workflow,
)
from mock_agents import ANALYSIS_MARKDOWN, RESEARCH_MARKDOWN, MockAgent

REQUEST = WorkflowRequest("Outlook", subject="ACME", topic="margins", period="FY2025")


def _run(research=None, analyst=None):
    research = research or MockAgent(RESEARCH_MARKDOWN)
    analyst = analyst or MockAgent(ANALYSIS_MARKDOWN)
    return run_workflow(REQUEST, research_fn=research, analyst_fn=analyst)


def _stage_error(research=None, analyst=None):
    with pytest.raises(WorkflowStageError) as exc:
        _run(research, analyst)
    return exc.value


# Success


def test_success_runs_agents_in_order_and_passes_parsed_research():
    research = MockAgent(RESEARCH_MARKDOWN)
    analyst = MockAgent(ANALYSIS_MARKDOWN)

    result = _run(research, analyst)

    assert research.calls == [(REQUEST,)]
    assert len(analyst.calls) == 1
    passed_request, passed_research = analyst.calls[0]
    assert passed_request == REQUEST
    assert isinstance(passed_research, ResearchReport)
    assert passed_research is result.research
    assert tuple(passed_research.sections) == research_agent.OUTPUT_SECTIONS


def test_success_result_holds_both_validated_stages():
    result = _run()
    assert result.request == REQUEST
    assert result.research.markdown == RESEARCH_MARKDOWN
    assert result.analysis.markdown == ANALYSIS_MARKDOWN
    assert tuple(result.analysis.sections) == investment_analyst.OUTPUT_SECTIONS


def test_final_report_contains_request_both_stages_and_disclaimer():
    report = _run().report_markdown

    assert report.startswith("# MAOS Investment Research Report\n\n> " + DISCLAIMER)
    assert report.rstrip().endswith("## Disclaimer\n\n" + DISCLAIMER)
    for line in (
        "- Research request: Outlook",
        "- Company or market: ACME",
        "- Research topic: margins",
        "- Relevant time period: FY2025",
    ):
        assert line in report
    for name in research_agent.OUTPUT_SECTIONS:
        assert f"### {name}\n\nResearch: {name} body." in report
    for name in investment_analyst.OUTPUT_SECTIONS:
        assert f"### {name}\n\nAnalysis: {name} body." in report
    assert report.index("## Part 1: Research") < report.index("## Part 2: Investment Analysis")


def test_disclaimer_says_not_investment_advice():
    assert "Not investment advice." in DISCLAIMER
    assert "not to give buy, sell, or hold recommendations" in DISCLAIMER


def test_workflow_is_deterministic():
    assert _run().report_markdown == _run().report_markdown


def test_fenced_research_output_is_accepted():
    result = _run(research=MockAgent(f"```markdown\n{RESEARCH_MARKDOWN}\n```"))
    assert result.research.sections["Limitations"] == "Research: Limitations body."


def test_default_agents_use_real_runner_with_shared_model(monkeypatch):
    """Both real agents run through Runner (faked) with the same model."""
    seen = []

    def fake_run_sync(agent, input, **kwargs):
        seen.append((agent.name, agent.model, input))
        outputs = {
            research_agent.AGENT_NAME: RESEARCH_MARKDOWN,
            investment_analyst.AGENT_NAME: ANALYSIS_MARKDOWN,
        }
        return SimpleNamespace(final_output=outputs[agent.name])

    monkeypatch.setattr(Runner, "run_sync", fake_run_sync)

    result = run_workflow(REQUEST, model="my-model")

    assert [(name, model) for name, model, _ in seen] == [
        (research_agent.AGENT_NAME, "my-model"),
        (investment_analyst.AGENT_NAME, "my-model"),
    ]
    assert seen[0][2] == research_agent.format_research_input(
        "Outlook", "ACME", "margins", "FY2025"
    )
    assert seen[1][2] == investment_analyst.format_analysis_input(REQUEST, result.research)


# Research stage failures: the analyst must never run.


@pytest.mark.parametrize(
    "error",
    [
        research_agent.EmptyResearchOutputError("the agent returned no output"),
        openai.APIConnectionError(request=None),
        RuntimeError("boom"),
    ],
    ids=["empty-output-error", "api-error", "unexpected"],
)
def test_research_failure_stops_before_analyst(error):
    analyst = MockAgent(ANALYSIS_MARKDOWN)
    exc = _stage_error(research=MockAgent(error=error), analyst=analyst)
    assert exc.stage == STAGE_RESEARCH
    assert exc.__cause__ is error
    assert analyst.calls == []


@pytest.mark.parametrize(
    ("output", "problem"),
    [
        (None, "output is empty"),
        ("", "output is empty"),
        ("No headings at all.", "missing section: Research Request"),
        (RESEARCH_MARKDOWN.replace("## Limitations", "## Caveats"), "missing section: Limitations"),
        (RESEARCH_MARKDOWN.replace("Research: Key Findings body.", ""), "empty section: Key Findings"),
        (RESEARCH_MARKDOWN + "\n\n## Recommendation\nBuy.", "unexpected section: 'Recommendation'"),
    ],
    ids=["none", "empty", "no-headings", "missing", "empty-section", "extra"],
)
def test_invalid_research_output_stops_before_analyst(output, problem):
    analyst = MockAgent(ANALYSIS_MARKDOWN)
    exc = _stage_error(research=MockAgent(output), analyst=analyst)
    assert exc.stage == STAGE_RESEARCH
    assert isinstance(exc.__cause__, OutputValidationError)
    assert problem in exc.__cause__.problems
    assert analyst.calls == []


# Analyst stage failures


@pytest.mark.parametrize(
    "error",
    [
        investment_analyst.EmptyAnalysisOutputError("the agent returned no output"),
        openai.APIConnectionError(request=None),
        RuntimeError("boom"),
    ],
    ids=["empty-output-error", "api-error", "unexpected"],
)
def test_analyst_failure_names_analyst_stage(error):
    research = MockAgent(RESEARCH_MARKDOWN)
    exc = _stage_error(research=research, analyst=MockAgent(error=error))
    assert exc.stage == STAGE_ANALYST
    assert exc.__cause__ is error
    assert len(research.calls) == 1


@pytest.mark.parametrize(
    ("output", "problem"),
    [
        ("", "output is empty"),
        (ANALYSIS_MARKDOWN.replace("## Risks", "## Threats"), "missing section: Risks"),
        (RESEARCH_MARKDOWN, "missing section: Analysis Request"),
    ],
    ids=["empty", "missing", "research-shaped"],
)
def test_invalid_analyst_output_names_analyst_stage(output, problem):
    exc = _stage_error(analyst=MockAgent(output))
    assert exc.stage == STAGE_ANALYST
    assert isinstance(exc.__cause__, OutputValidationError)
    assert problem in exc.__cause__.problems


def test_stage_error_message_does_not_include_cause_text():
    exc = _stage_error(research=MockAgent(error=RuntimeError("secret sk-test-XYZ")))
    assert str(exc) == "research stage failed"


def test_keyboard_interrupt_is_not_wrapped():
    with pytest.raises(KeyboardInterrupt):
        _run(research=MockAgent(error=KeyboardInterrupt()))


def test_keyboard_interrupt_in_analyst_stage_is_not_wrapped():
    research = MockAgent(RESEARCH_MARKDOWN)
    with pytest.raises(KeyboardInterrupt):
        _run(research=research, analyst=MockAgent(error=KeyboardInterrupt()))
    assert len(research.calls) == 1


def test_analyst_cannot_modify_research_sections():
    def mutating_analyst(request, research):
        research.sections["Key Findings"] = "tampered"
        return ANALYSIS_MARKDOWN

    exc = _stage_error(analyst=mutating_analyst)
    assert exc.stage == STAGE_ANALYST
    assert isinstance(exc.__cause__, TypeError)


# Review fixes M1, M2, L1 through the workflow


def test_unclosed_fence_in_research_stops_before_analyst():
    analyst = MockAgent(ANALYSIS_MARKDOWN)
    output = RESEARCH_MARKDOWN + "\n```\nstray"
    exc = _stage_error(research=MockAgent(output), analyst=analyst)
    assert exc.stage == STAGE_RESEARCH
    assert exc.__cause__.problems == ("unclosed code fence in section: Limitations",)
    assert analyst.calls == []


def test_unclosed_fence_in_analysis_names_analyst_stage():
    output = ANALYSIS_MARKDOWN.replace("Analysis: Risks body.", "```\nopen")
    exc = _stage_error(analyst=MockAgent(output))
    assert exc.stage == STAGE_ANALYST
    assert exc.__cause__.problems[0] == "unclosed code fence in section: Risks"


def test_report_fences_stay_balanced_with_fenced_blocks_in_sections():
    research = RESEARCH_MARKDOWN.replace(
        "Research: Key Findings body.", "```markdown\n## Example\n```"
    )
    report = _run(research=MockAgent(research)).report_markdown
    assert "```markdown\n## Example\n```" in report
    assert sum(line.startswith("```") for line in report.splitlines()) % 2 == 0
    assert report.rstrip().endswith("## Disclaimer\n\n" + DISCLAIMER)


def test_crlf_and_closing_hash_output_is_accepted():
    research = RESEARCH_MARKDOWN.replace("## Limitations", "## Limitations ##")
    result = _run(research=MockAgent(research.replace("\n", "\r\n")))
    assert result.research.sections["Limitations"] == "Research: Limitations body."
    assert "\r" not in result.report_markdown
