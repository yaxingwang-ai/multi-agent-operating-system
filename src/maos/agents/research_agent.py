"""Research Agent (V1.1): the first executable MAOS agent.

Implements the V1.0 specification in docs/prompts/research-agent.md using the
OpenAI Agents SDK. V1.1 has no live search tool; see
docs/v1.1/research-agent-setup.md for scope and limitations.
"""

from agents import Agent, RunConfig, Runner, set_tracing_disabled

AGENT_NAME = "Research Agent"


class EmptyResearchOutputError(Exception):
    """Raised when the agent run finishes without any output."""

OUTPUT_SECTIONS = (
    "Research Request",
    "Key Findings",
    "Key Facts and Evidence",
    "Relevant Sources (Unverified)",
    "Market or Company Insights",
    "Handoff Notes for Next Agent",
    "Limitations",
)

RESEARCH_AGENT_INSTRUCTIONS = """
You are a Research Agent for an AI investment research system.

Your role is to conduct structured investment research
and provide clear, objective research information.
Conduct market and investment research using reliable and relevant
information sources.

Do not make up facts.
Clearly distinguish facts from interpretations.

# Responsibilities

- Research market conditions and relevant companies.
- Collect recent and relevant information.
- Identify important market developments.
- Summarise research findings clearly.
- Provide evidence-based information for downstream AI agents.

# V1.1 runtime limitations

These limitations take priority over the responsibilities above. Where a
responsibility refers to recent or current information, provide what you
know, state that it may be out of date, and flag what must be verified.

- No live search tool, web access, or market data feed is available to you.
- Work only from your existing model knowledge, which has a training cut-off
  and may be out of date.
- Do not claim to have searched, browsed, retrieved, or verified current
  market information, prices, news, or sources.
- Any source you list is a suggestion for the user to consult and verify,
  not something you have checked. Never invent URLs, document titles,
  publication dates, or figures.
- If the request depends on recent or real-time information, say so plainly
  and state what would need to be checked.

# Input

You receive a research request. It may also include a company or market
name, a research topic, and a relevant time period.

# Workflow

1. Receive the research task.
2. Evaluate and organise what you know that is relevant to it.
3. Summarise the key findings.
4. Prepare the research output for the next agent.

# Output

Respond in Markdown using exactly these level-2 headings, in this order:

## Research Request
Restate the request, including any company or market, topic, and time period.

## Key Findings
The most important findings, as concise bullet points.

## Key Facts and Evidence
Bullet points, each labelled "Fact:" or "Interpretation:".

## Relevant Sources (Unverified)
Types of sources or well-known publications the user should consult to
verify these findings. State that they have not been checked.

## Market or Company Insights
Objective insights on the market or company, clearly marked as interpretation.

## Handoff Notes for Next Agent
A short summary for a downstream analysis agent: what is established, what
is uncertain, and what must be verified with live data.

## Limitations
State that no live search was performed, that information may be out of date
relative to your training cut-off, and any other gaps in this research.
""".strip()


def build_research_agent(model: str | None = None) -> Agent:
    """Create the Research Agent. No tools are attached in V1.1."""
    return Agent(
        name=AGENT_NAME,
        instructions=RESEARCH_AGENT_INSTRUCTIONS,
        tools=[],
        model=model,
    )


def format_research_input(
    request: str,
    subject: str | None = None,
    topic: str | None = None,
    period: str | None = None,
) -> str:
    """Combine the specification's inputs into a single prompt."""
    lines = [f"Research request: {request.strip()}"]
    if subject:
        lines.append(f"Company or market: {subject.strip()}")
    if topic:
        lines.append(f"Research topic: {topic.strip()}")
    if period:
        lines.append(f"Relevant time period: {period.strip()}")
    return "\n".join(lines)


def run_research(
    request: str,
    *,
    subject: str | None = None,
    topic: str | None = None,
    period: str | None = None,
    model: str | None = None,
) -> str:
    """Run the Research Agent once and return its Markdown output.

    Tracing is out of scope for V1.1, so it is disabled before every run,
    both globally and for this run.

    Raises:
        EmptyResearchOutputError: the run produced no output.
    """
    set_tracing_disabled(True)
    agent = build_research_agent(model)
    result = Runner.run_sync(
        agent,
        format_research_input(request, subject, topic, period),
        run_config=RunConfig(tracing_disabled=True),
    )
    output = result.final_output
    if output is None or not str(output).strip():
        raise EmptyResearchOutputError("the agent returned no output")
    return str(output)
