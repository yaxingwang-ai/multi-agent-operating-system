import re
from types import SimpleNamespace

import pytest
from agents import Runner, set_tracing_disabled
from agents.tracing import get_trace_provider
from agents.tracing.traces import NoOpTrace

from maos.agents import research_agent
from maos.agents.investment_analyst import (
    AGENT_NAME,
    INVESTMENT_ANALYST_INSTRUCTIONS,
    OUTPUT_SECTION_GUIDANCE,
    OUTPUT_SECTIONS,
    EmptyAnalysisOutputError,
    build_investment_analyst,
    format_analysis_input,
    run_investment_analysis,
)
from maos.contracts import ResearchReport, WorkflowRequest, parse_sections
from mock_agents import RESEARCH_MARKDOWN

REQUEST = WorkflowRequest("Outlook", subject="ACME", period="FY2025")
RESEARCH = ResearchReport(
    sections=parse_sections(RESEARCH_MARKDOWN, research_agent.OUTPUT_SECTIONS),
    markdown=RESEARCH_MARKDOWN,
)


def test_preserves_spec_name_role_and_honesty_rules():
    assert AGENT_NAME == "Investment Analyst"
    for line in (
        "You are the Investment Analyst within an AI Multi-Agent System for Investment Research.",
        "Do not invent financial data, company information or market events.",
        "When information is incomplete or uncertain, clearly state the limitation.",
    ):
        assert line in INVESTMENT_ANALYST_INSTRUCTIONS


def test_instructions_state_no_live_data():
    text = INVESTMENT_ANALYST_INSTRUCTIONS
    assert "No live search tool, web access, or market data feed" in text
    assert "Never invent figures, prices, dates, sources, or events." in text
    assert "These limitations take priority over the responsibilities above." in text


def test_instructions_forbid_investment_recommendations():
    text = INVESTMENT_ANALYST_INSTRUCTIONS
    assert "Do not give buy, sell, or hold recommendations." in text
    assert "Do not give price targets, ratings, or portfolio allocation advice." in text
    assert "this is not investment advice" in OUTPUT_SECTION_GUIDANCE["Limitations"]


def test_output_sections_follow_spec_output_list():
    assert OUTPUT_SECTIONS == (
        "Analysis Request",
        "Key Findings",
        "Financial and Business Observations",
        "Opportunities",
        "Risks",
        "Assumptions",
        "Key Uncertainties",
        "Supporting Evidence",
        "Handoff Notes for Report Generator",
        "Limitations",
    )


def test_instruction_headings_are_exactly_output_sections():
    headings = re.findall(
        r"^## (.+)$", INVESTMENT_ANALYST_INSTRUCTIONS, flags=re.MULTILINE
    )
    assert tuple(headings) == OUTPUT_SECTIONS


def test_each_section_heading_is_followed_by_its_guidance():
    for name, guidance in OUTPUT_SECTION_GUIDANCE.items():
        assert guidance.strip()
        assert f"## {name}\n{guidance}" in INVESTMENT_ANALYST_INSTRUCTIONS


def test_agent_has_no_tools_and_default_model():
    agent = build_investment_analyst()
    assert agent.name == AGENT_NAME
    assert agent.tools == []
    assert agent.model is None


def test_agent_model_override():
    assert build_investment_analyst("my-model").model == "my-model"


def test_input_includes_request_and_every_research_section():
    text = format_analysis_input(REQUEST, RESEARCH)
    assert text.startswith(
        "Original user request:\n\n"
        "Research request: Outlook\n"
        "Company or market: ACME\n"
        "Relevant time period: FY2025\n\n"
        "Research Agent findings (from model knowledge only, unverified):"
    )
    for name, body in RESEARCH.sections.items():
        assert f"### {name}\n{body}" in text


def test_input_has_no_level_two_headings():
    """The analyst's own output headings must not appear in its input."""
    assert not re.search(r"^## ", format_analysis_input(REQUEST, RESEARCH), re.MULTILINE)


def test_run_uses_runner(monkeypatch):
    calls = {}

    def fake_run_sync(agent, input, **kwargs):
        calls["agent"] = agent
        calls["input"] = input
        return SimpleNamespace(final_output="## Analysis Request\nok")

    monkeypatch.setattr(Runner, "run_sync", fake_run_sync)

    output = run_investment_analysis(REQUEST, RESEARCH, model="my-model")

    assert output == "## Analysis Request\nok"
    assert calls["agent"].name == AGENT_NAME
    assert calls["agent"].model == "my-model"
    assert calls["input"] == format_analysis_input(REQUEST, RESEARCH)


def test_run_disables_tracing_before_sdk_run(monkeypatch):
    set_tracing_disabled(False)
    observed = {}

    def fake_run_sync(agent, input, **kwargs):
        observed["trace"] = get_trace_provider().create_trace("check")
        observed["run_config"] = kwargs.get("run_config")
        return SimpleNamespace(final_output="ok")

    monkeypatch.setattr(Runner, "run_sync", fake_run_sync)

    run_investment_analysis(REQUEST, RESEARCH)

    assert isinstance(observed["trace"], NoOpTrace)
    assert observed["run_config"].tracing_disabled is True


@pytest.mark.parametrize("final_output", [None, "", "  \n "], ids=["none", "empty", "blank"])
def test_empty_output_raises(monkeypatch, final_output):
    monkeypatch.setattr(
        Runner, "run_sync",
        lambda agent, input, **kwargs: SimpleNamespace(final_output=final_output),
    )
    with pytest.raises(EmptyAnalysisOutputError):
        run_investment_analysis(REQUEST, RESEARCH)
