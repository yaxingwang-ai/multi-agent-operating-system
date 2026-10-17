from types import SimpleNamespace

import pytest
from agents import Runner, set_tracing_disabled
from agents.tracing import get_trace_provider
from agents.tracing.traces import NoOpTrace

from maos.agents.research_agent import (
    AGENT_NAME,
    OUTPUT_SECTIONS,
    RESEARCH_AGENT_INSTRUCTIONS,
    EmptyResearchOutputError,
    build_research_agent,
    format_research_input,
    run_research,
)


def test_preserves_original_name_role_and_honesty_rules():
    assert AGENT_NAME == "Research Agent"
    for line in (
        "You are a Research Agent for an AI investment research system.",
        "Your role is to conduct structured investment research",
        "and provide clear, objective research information.",
        "Do not make up facts.",
        "Clearly distinguish facts from interpretations.",
    ):
        assert line in RESEARCH_AGENT_INSTRUCTIONS


def test_instructions_state_no_live_search():
    text = RESEARCH_AGENT_INSTRUCTIONS
    assert "No live search tool" in text
    assert "Do not claim to have searched, browsed, retrieved, or verified" in text
    assert "Never invent URLs, document titles," in text
    assert "publication dates, or figures." in text


def test_limitations_take_priority_over_responsibilities():
    text = RESEARCH_AGENT_INSTRUCTIONS
    assert "These limitations take priority over the responsibilities above." in text
    assert text.index("# Responsibilities") < text.index("# V1.1 runtime limitations")


def test_instructions_list_every_output_section_in_order():
    positions = [
        RESEARCH_AGENT_INSTRUCTIONS.index(f"## {section}")
        for section in OUTPUT_SECTIONS
    ]
    assert positions == sorted(positions)


def test_agent_has_no_tools_and_default_model():
    agent = build_research_agent()
    assert agent.name == AGENT_NAME
    assert agent.tools == []
    assert agent.model is None


def test_agent_model_override():
    assert build_research_agent("my-model").model == "my-model"


def test_format_input_with_all_fields():
    text = format_research_input(
        " Outlook ", subject="ACME Corp", topic="margins", period="FY2025"
    )
    assert text == (
        "Research request: Outlook\n"
        "Company or market: ACME Corp\n"
        "Research topic: margins\n"
        "Relevant time period: FY2025"
    )


def test_format_input_with_request_only():
    assert format_research_input("Outlook") == "Research request: Outlook"


def test_run_research_uses_runner(monkeypatch):
    calls = {}

    def fake_run_sync(agent, input, **kwargs):
        calls["agent"] = agent
        calls["input"] = input
        return SimpleNamespace(final_output="## Research Request\nok")

    monkeypatch.setattr(Runner, "run_sync", fake_run_sync)

    output = run_research("Outlook", subject="ACME", model="my-model")

    assert output == "## Research Request\nok"
    assert calls["agent"].model == "my-model"
    assert calls["input"] == "Research request: Outlook\nCompany or market: ACME"


def test_direct_run_research_disables_tracing_before_sdk_run(monkeypatch):
    # Start from an enabled state to prove run_research() itself disables it.
    set_tracing_disabled(False)
    observed = {}

    def fake_run_sync(agent, input, **kwargs):
        observed["trace"] = get_trace_provider().create_trace("check")
        observed["run_config"] = kwargs.get("run_config")
        return SimpleNamespace(final_output="ok")

    monkeypatch.setattr(Runner, "run_sync", fake_run_sync)

    run_research("Outlook")

    assert isinstance(observed["trace"], NoOpTrace)
    assert observed["run_config"].tracing_disabled is True


@pytest.mark.parametrize("final_output", [None, "", "  \n "], ids=["none", "empty", "blank"])
def test_empty_output_raises(monkeypatch, final_output):
    monkeypatch.setattr(
        Runner, "run_sync",
        lambda agent, input, **kwargs: SimpleNamespace(final_output=final_output),
    )
    with pytest.raises(EmptyResearchOutputError):
        run_research("Outlook")
