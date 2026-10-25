# Multi-Agent Workflow (V1.2)

## Purpose

V1.2 connects two agents into one workflow, run from the command line:

```text
User Request
   │
   ▼
Research Agent          (unchanged from V1.1)
   │  Markdown
   ▼
Validate research       (Python, no AI)   ── invalid → stop
   │  ResearchReport
   ▼
Investment Analyst      (new in V1.2)
   │  Markdown
   ▼
Validate analysis       (Python, no AI)   ── invalid → stop
   │  InvestmentAnalysis
   ▼
Final Report            (Python template, no AI)
```

The Investment Analyst implements the V1.0 specification in
[`docs/prompts/investment-analyst.md`](../prompts/investment-analyst.md),
which is unchanged. V1.2 adds runtime limits to it: no live data, and an
instruction not to give investment recommendations.

The V1.1 Research Agent command, `maos-research`, works exactly as before.

## Scope and Limitations

Included in V1.2:

- Investment Analyst agent, run with `Runner`
- `maos-workflow` command running both agents in sequence
- Validation of each agent's output before it is passed on
- A final Markdown report with a "not investment advice" disclaimer
- Offline tests using mock agents

Not included in V1.2:

- Live search, market data, or any other tools
- The Report Generator, Risk Manager, Portfolio Manager, or Market Monitor
  agents. The final report is assembled by a fixed template.
- Automatic retries
- MySQL, n8n, MCP, HTTP API
- Tracing (explicitly disabled before every agent run)

Both agents answer from model knowledge only. Their facts and sources have
not been verified and may be out of date. The Investment Analyst is
instructed never to give buy, sell, or hold recommendations, price targets,
ratings, or allocation advice. This is a prompt instruction, so it is not
guaranteed. **The report is not investment advice.**

## Installation

Follow the [V1.1 setup guide](../v1.1/research-agent-setup.md). If you
installed V1.1 earlier, reinstall so the new `maos-workflow` command is
registered:

```bash
pip install -e ".[dev]" -c constraints.txt
```

Configuration is the same as V1.1. Both agents use `MAOS_RESEARCH_MODEL`
(or the SDK default model when it is empty).

## Usage

```bash
maos-workflow "Assess the investment case for the company" \
  --subject "ACME Corp" \
  --topic "competitive landscape" \
  --period "last 12 months"
```

The arguments are the same as `maos-research`. A successful run makes
**two** model calls, one per agent; if the research stage fails, the analyst
is not called. The OpenAI SDK retries some failed requests (such as
connection errors, rate limits, and server errors) automatically, so the
number of HTTP requests, and the API cost, can be higher than the number of
model calls.

To save the report: `maos-workflow "..." > report.md`

### Final Report

```text
# MAOS Investment Research Report
> Not investment advice disclaimer
## Request
## Part 1: Research               (the 7 Research Agent sections)
## Part 2: Investment Analysis    (the 10 Investment Analyst sections)
## Disclaimer
```

The report contains no date or other changing content, so the same agent
outputs always produce the same report.

## Architecture

The workflow core is designed to be reused by the current CLI and a future
API or web interface. V1.2 adds no web framework, HTTP API, or new
dependency.

```text
CLI (maos-research, maos-workflow)      future API layer
        │  parse args, print, exit codes        │  JSON, HTTP status codes
        └──────────────┬───────────────────────┘
                       ▼
   contracts.py   WorkflowRequest → WorkflowResult   (validated data)
   workflow.py    run_workflow()                     (no printing, no I/O)
   errors.py      safe error descriptions            (shared by all interfaces)
                       │
                       ▼
   agents/        run_research(), run_investment_analysis()  (model calls)
```

- **No CLI code in the core.** `contracts.py`, `workflow.py`, and
  `errors.py` never print or read arguments, and do not import `argparse`
  or the CLI modules (checked by `tests/test_architecture.py`).
- **Validated contracts.** `WorkflowRequest` checks its own input when it is
  created, so every interface gets the same rules.
- **Results or exceptions.** `run_workflow()` returns a `WorkflowResult` or
  raises `WorkflowStageError`. Each interface decides how to present them.
- **Replaceable model calls.** Agent calls are plain functions, and
  `run_workflow()` takes `research_fn` and `analyst_fn`, so tests (or later
  versions) can substitute them.
- **Shared safe errors.** `errors.describe_stage_error()` turns any failure
  into a message that never contains raw SDK text or the API key.
- **V1.1 stays independent.** `maos-research` does not load `workflow.py`
  or the Investment Analyst (also checked by `tests/test_architecture.py`).

Known gaps for a future API layer, intentionally left out of V1.2:

- `run_workflow()` is synchronous (it uses `Runner.run_sync`). An async web
  server would need an async variant using `Runner.run`.
- The API key is set once per process with `set_default_openai_key`, which
  suits one server-wide key but not per-user keys.
- Results are dataclasses. A JSON conversion (and request length limits)
  would be added with the API.

## Data Contracts

Defined in `src/maos/contracts.py`. Each one is a read-only dataclass.

| Contract | Produced by | Contents |
|---|---|---|
| `WorkflowRequest` | CLI (or a future API) | `request` (required, non-blank text), optional `subject`, `topic`, `period` (text or `None`). Values are stripped; blank optional values become `None`. Invalid input raises `ValueError`. |
| `ResearchReport` | Research validation | `sections` (the 7 Research Agent sections), `markdown` (raw output) |
| `InvestmentAnalysis` | Analyst validation | `sections` (the 10 Investment Analyst sections), `markdown` |
| `WorkflowResult` | Workflow | the request, both stage results, and `report_markdown` |

Section bodies are read-only, so a later stage cannot change an earlier
stage's output.

### Required Sections

Research Agent, unchanged from V1.1:

1. Research Request
2. Key Findings
3. Key Facts and Evidence
4. Relevant Sources (Unverified)
5. Market or Company Insights
6. Handoff Notes for Next Agent
7. Limitations

Investment Analyst, from the Output list in its V1.0 specification:

1. Analysis Request
2. Key Findings
3. Financial and Business Observations
4. Opportunities
5. Risks
6. Assumptions
7. Key Uncertainties
8. Supporting Evidence
9. Handoff Notes for Report Generator
10. Limitations

### Validation Rules

An agent's output is valid only if:

- Every required `## ` heading is present, spelled exactly.
- No heading appears twice, and none is out of order.
- There are no other `## ` headings.
- No section body is empty.
- Every fenced code block (```` ``` ```` or `~~~`) is closed. An unclosed
  fence would turn the rest of the final report into a code block, so it is
  rejected.

Allowed:

- Text before the first `## ` heading (ignored).
- `###` subheadings inside a section.
- A single code fence around the whole output.
- Windows (CRLF) line endings.
- Closing hashes, such as `## Limitations ##`.
- Up to three leading spaces before a heading's `##`, such as
  `   ## Limitations`. Indented headings are checked like any other, so an
  indented unexpected heading is still rejected. With four or more spaces
  the line is treated as section text, not a heading.
- `## ` lines inside a fenced code block, which are treated as section text,
  not headings.

Still rejected, so section names stay exact: bold headings
(`## **Limitations**`), numbered headings (`## 7. Limitations`), and any
other change to a heading's text.

Known limitation: only `##`-style headings are checked, so a Setext-style
heading (a line of text followed by a line of `---` or `===`) is not
detected and can appear as an extra heading in the final report.

A validation error lists at most five problems, followed by a count of the
rest (for example, `...; and 3 more problems`). The exception's `problems`
attribute keeps the full list.

The Investment Analyst receives the original request plus each validated
research section as a `###` heading.

## Failure Handling

The workflow stops at the first failed stage. If the research stage fails,
the Investment Analyst is never called. No partial report is printed.

| Failure | Message (stderr) | Exit code |
|---|---|---|
| Missing or placeholder API key | Same as V1.1 | 2 |
| Agent returned no output | `Error: <stage> stage: the agent returned no output.` | 1 |
| Output failed validation | `Error: <stage> stage: the agent's output was invalid (<problems>).` | 1 |
| OpenAI or SDK error | `Error: <stage> stage: <same message as V1.1>` | 1 |
| Interrupted (Ctrl+C) | `Error: interrupted.` | 130 |

`<stage>` is `research` or `analyst`. Raw OpenAI and SDK error messages,
which can contain part of the API key, are never printed. The API key
safety rules in the V1.1 guide apply unchanged.

## Testing

```bash
pytest
```

All tests are offline, using the same guards as V1.1 (see
`tests/conftest.py`). The workflow tests use mock agents (`tests/mock_agents.py`)
that return fixed Markdown or raise an error, so results are deterministic.

| Test file | Covers |
|---|---|
| `tests/test_contracts.py` | Section validation rules and the request contract |
| `tests/test_investment_analyst.py` | Analyst prompt, sections, input format, and run |
| `tests/test_workflow.py` | Stage order, data passed between stages, report, and each failure case |
| `tests/test_workflow_cli.py` | Exit codes, error messages, no key leaks at either stage (including in a fresh interpreter), tracing disabled, Ctrl+C |
| `tests/test_packaging.py` | Both commands are registered in `pyproject.toml` and resolve to the right functions (no install needed) |
| `tests/test_architecture.py` | Core has no CLI imports, never prints, and shared errors work without a CLI |

### Live Smoke Test (optional)

A successful run makes two model calls and uses API credit (more HTTP
requests if the SDK retries). With `.env` configured:

```bash
maos-workflow "Give an overview of the global semiconductor industry"
```

Check that:

- The exit code is 0 (`echo $?`).
- The report contains both parts and the disclaimer at the top and bottom.
- The analysis contains no buy, sell, or hold recommendation. The analyst
  is only instructed not to give one, so check.
- No section claims that sources or current data were verified.

A live run has not yet been verified for V1.2. A model may sometimes miss
the required headings; the workflow then exits with a validation error
rather than printing a malformed report. Retry, or try another model.

## Project Structure

```text
src/maos/
├── __init__.py                  Package version (1.2.0)
├── __main__.py                  Enables `python -m maos` (Research Agent)
├── cli.py                       maos-research CLI and shared CLI helpers
├── config.py                    Environment configuration
├── contracts.py                 Stage data contracts and section validation
├── errors.py                    Safe error descriptions shared by all interfaces
├── workflow.py                  Workflow orchestration and final report
├── workflow_cli.py              maos-workflow CLI
└── agents/
    ├── research_agent.py        Research Agent (V1.1)
    └── investment_analyst.py    Investment Analyst (V1.2)
```
