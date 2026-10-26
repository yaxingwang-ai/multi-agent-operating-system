"""Investment Analyst (V1.2): the second executable MAOS agent.

Implements the V1.0 specification in docs/prompts/investment-analyst.md using
the OpenAI Agents SDK. It analyses validated Research Agent output and has no
tools; see docs/v1.2/multi-agent-workflow.md for scope and limitations.
"""

from agents import Agent, RunConfig, Runner, set_tracing_disabled

from maos.agents.research_agent import format_research_input
from maos.contracts import EmptyAnalysisOutputError, ResearchReport, WorkflowRequest

AGENT_NAME = "Investment Analyst"

# Output headings and their guidance, in order. The Output block of the
# instructions is generated from this, so the two cannot drift apart.
OUTPUT_SECTION_GUIDANCE = {
    "Analysis Request": "Restate what is being analysed, based on the original request.",
    "Key Findings": "The most important analytical findings, as concise bullet points.",
    "Financial and Business Observations": (
        'Bullet points, each labelled "Fact:" or "Interpretation:".'
    ),
    "Opportunities": "Potential opportunities, clearly marked as interpretation.",
    "Risks": "Potential risks, clearly marked as interpretation.",
    "Assumptions": "The key assumptions behind this analysis.",
    "Key Uncertainties": (
        "What is uncertain or unknown, and what must be verified with live data."
    ),
    "Supporting Evidence": (
        "Which research findings support the analysis. Do not add new sources."
    ),
    "Handoff Notes for Report Generator": (
        "A short summary for the report: what is established, what is uncertain,\n"
        "and what must be verified."
    ),
    "Limitations": (
        "State that the analysis is based only on the research provided, that no\n"
        "live data was used, and that this is not investment advice."
    ),
}

OUTPUT_SECTIONS = tuple(OUTPUT_SECTION_GUIDANCE)

_BASE_INSTRUCTIONS = """
You are the Investment Analyst within an AI Multi-Agent System for Investment Research.

Your role is to analyse research findings, company information, financial data
and market context provided by the Research Agent.

Your analysis must be structured, evidence-based and clearly distinguish facts
from interpretation.

Do not invent financial data, company information or market events.

When information is incomplete or uncertain, clearly state the limitation.

# Responsibilities

- Analyse research findings provided by the Research Agent.
- Evaluate company and market information.
- Identify important financial and business factors.
- Analyse potential opportunities and risks.
- Compare relevant companies or investment themes when required.
- Identify key assumptions behind the analysis.
- Summarise important findings for the next agent.
- Provide evidence-based conclusions without presenting unsupported claims.

# V1.2 runtime limitations

These limitations take priority over the responsibilities above.

- No live search tool, web access, or market data feed is available to you.
- The research you receive was produced from model knowledge only. Its facts
  and sources have not been verified and may be out of date.
- Base your analysis on that research. If you add general background
  knowledge, label it as interpretation and note that it is unverified.
- Never invent figures, prices, dates, sources, or events.
- Do not claim to have searched, retrieved, or verified any information.

# No investment advice

- Do not give buy, sell, or hold recommendations.
- Do not give price targets, ratings, or portfolio allocation advice.
- Do not tell the user what to do with their money.
- Present opportunities and risks for the user to weigh, not decisions.

# Workflow

1. Receive research findings from the Research Agent.
2. Review the available information and identify relevant evidence.
3. Analyse the company, market or investment topic.
4. Identify important financial and business factors.
5. Evaluate opportunities and risks.
6. Identify assumptions and uncertainties.
7. Structure the analysis into a clear format.
8. Check that important claims are supported by available evidence.

# Output

Respond in Markdown using exactly these level-2 headings, in this order.
Do not add any other level-2 headings:
""".strip()

INVESTMENT_ANALYST_INSTRUCTIONS = "\n\n".join(
    [_BASE_INSTRUCTIONS]
    + [f"## {name}\n{guidance}" for name, guidance in OUTPUT_SECTION_GUIDANCE.items()]
)


def build_investment_analyst(model: str | None = None) -> Agent:
    """Create the Investment Analyst. No tools are attached in V1.2."""
    return Agent(
        name=AGENT_NAME,
        instructions=INVESTMENT_ANALYST_INSTRUCTIONS,
        tools=[],
        model=model,
    )


def format_analysis_input(request: WorkflowRequest, research: ResearchReport) -> str:
    """Combine the original request and the validated research into one prompt.

    Research sections are given as level-3 headings so they cannot be
    mistaken for the level-2 headings the analyst must produce.
    """
    parts = [
        "Original user request:",
        format_research_input(
            request.request, request.subject, request.topic, request.period
        ),
        "Research Agent findings (from model knowledge only, unverified):",
    ]
    parts += [f"### {name}\n{body}" for name, body in research.sections.items()]
    return "\n\n".join(parts)


def run_investment_analysis(
    request: WorkflowRequest,
    research: ResearchReport,
    *,
    model: str | None = None,
) -> str:
    """Run the Investment Analyst once and return its Markdown output.

    Tracing is out of scope for V1.2, so it is disabled before every run,
    both globally and for this run.

    Raises:
        EmptyAnalysisOutputError: the run produced no output.
    """
    set_tracing_disabled(True)
    agent = build_investment_analyst(model)
    result = Runner.run_sync(
        agent,
        format_analysis_input(request, research),
        run_config=RunConfig(tracing_disabled=True),
    )
    output = result.final_output
    if output is None or not str(output).strip():
        raise EmptyAnalysisOutputError("the agent returned no output")
    return str(output)
