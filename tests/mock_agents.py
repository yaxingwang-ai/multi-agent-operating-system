"""Deterministic mock agents and sample outputs for the V1.2 workflow tests."""

from maos.agents import investment_analyst, research_agent


def make_markdown(sections, prefix=""):
    """Build agent-style Markdown with one placeholder body per section."""
    return "\n\n".join(
        f"## {name}\n{prefix}{name} body." for name in sections
    )


RESEARCH_MARKDOWN = make_markdown(research_agent.OUTPUT_SECTIONS, "Research: ")
ANALYSIS_MARKDOWN = make_markdown(investment_analyst.OUTPUT_SECTIONS, "Analysis: ")


class MockAgent:
    """Records each call, then returns a fixed output or raises an error."""

    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        if self.error is not None:
            raise self.error
        return self.output
