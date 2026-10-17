# Research Agent Setup (V1.1)

## Purpose

V1.1 delivers the first executable Research Agent, built with the
OpenAI Agents SDK and run from the command line.

The agent implements the V1.0 specification in
[`docs/prompts/research-agent.md`](../prompts/research-agent.md), which is
unchanged.

## Scope and Limitations

Included in V1.1:

- OpenAI Agents SDK agent run with `Runner`
- Command-line input
- Structured Markdown output
- Environment-based configuration
- Basic error handling
- Offline tests

Not included in V1.1:

- Live search or any other tools. The V1.0 specification names Perplexity;
  it is not used in V1.1.
- Handoff to the Financial Analyst or any other agent
- MySQL, n8n, MCP, HTTP API
- Tracing (explicitly disabled before every run)

Roadmap:

| Version | Focus |
|---|---|
| V1.1 | First executable Research Agent |
| V1.2 | Multi-Agent Workflow |
| V1.3 | Tools and APIs |
| V1.4 | MCP |

Because no search tool is available, the agent answers from model knowledge
only. It is instructed not to claim it has verified current market
information or sources, and to list sources as **unverified** suggestions.
Do not use its output as current market data.

## Requirements

- Python 3.10 or later. The offline tests were run with Python 3.14.3.
  A live API request has not yet been verified.
- An OpenAI API key with access to the Responses API

## Project Structure

```text
src/maos/
├── __init__.py              Package version
├── __main__.py              Enables `python -m maos`
├── cli.py                   Command-line interface and error handling
├── config.py                Environment configuration
└── agents/
    └── research_agent.py    Research Agent definition and runner
tests/                       Offline tests (no API key, no network)
```

The package is imported as `maos`, so `maos.agents` does not conflict with
the OpenAI Agents SDK's top-level `agents` package.

## Installation

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]" -c constraints.txt
```

Direct dependencies are pinned in `pyproject.toml`. `constraints.txt` pins
every other installed package to the versions from the V1.1 development
environment (Python 3.14.3, macOS), so installs resolve the same versions.

To refresh `constraints.txt` after an intentional dependency change:

```bash
pip freeze --exclude-editable > constraints.txt
```

Then restore the header comment at the top of the file.

## Configuration

Copy the example file and add your own key:

```bash
cp .env.example .env
```

Then edit `.env`:

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Your OpenAI API key |
| `MAOS_RESEARCH_MODEL` | No | Model name. Leave empty to use the SDK default |

Variables already exported in your shell take precedence over `.env`.

### API Key Safety

- `.env` and `.env.*` files are excluded by `.gitignore`, except
  `.env.example`. Never commit them.
- `.env.example` contains placeholders only. Never put a real key in it.
- Never put a key in source code, tests, logs, or commit messages.
- The CLI never prints the key, and does not print OpenAI error messages,
  which can contain part of it.
- Check before committing: `git status` must not list `.env`.

## Usage

Supported entry points, with the virtual environment activated:

- `maos-research`
- `python -m maos`

```bash
maos-research "Summarise the competitive position of the company" \
  --subject "ACME Corp" \
  --topic "competitive landscape" \
  --period "last 12 months"
```

| Argument | Required | Specification input |
|---|---|---|
| `request` | Yes | User research request |
| `--subject` | No | Company or market name |
| `--topic` | No | Research topic |
| `--period` | No | Relevant time period |

### Output

Markdown with these sections, in order:

1. Research Request
2. Key Findings
3. Key Facts and Evidence
4. Relevant Sources (Unverified)
5. Market or Company Insights
6. Handoff Notes for Next Agent
7. Limitations

To save the output: `maos-research "..." > research.md`

### Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Run failed (authentication, rate limit, connection, API, or agent error; empty output; unexpected error) |
| 2 | Configuration or argument error (for example, missing `OPENAI_API_KEY`) |
| 130 | Interrupted |

## Testing

### Offline Tests

```bash
pytest
```

The tests need no API key and make no network calls. Fixtures in
`tests/conftest.py`:

- Clear `OPENAI_API_KEY` and `MAOS_RESEARCH_MODEL`, and skip loading `.env`.
- Block outbound socket connections and DNS lookups.
- Fail any test that reaches the real `Runner.run_sync` or `Runner.run`.

`tests/test_offline_guard.py` checks that these guards trigger. The tests use
a fake key only to check it is never printed.

### Live Smoke Test (optional)

This makes one real API call and uses API credit. With `.env` configured:

```bash
maos-research "Give an overview of the global semiconductor industry"
```

Check that:

- The exit code is 0 (`echo $?`).
- All seven output sections are present.
- The Limitations section states that no live search was performed.
- No section claims that sources or current data were verified.

## Troubleshooting

| Message | Fix |
|---|---|
| `OPENAI_API_KEY is not set` | Create `.env` from `.env.example`, or export the variable |
| `still contains the placeholder` | Replace the placeholder in `.env` with your key |
| `OpenAI rejected the API key` | Check the key is valid and active |
| `rate limit or quota exceeded` | Wait, or check your OpenAI billing and usage limits |
| `could not connect to the OpenAI API` | Check your network or proxy settings |
| `OpenAI API returned HTTP 400` or `404` | Check `MAOS_RESEARCH_MODEL` names a model your key can use |
| `the agent returned no output` | Retry; if it persists, try another model |
| `ModuleNotFoundError: No module named 'maos'` | Activate `.venv` and run `pip install -e ".[dev]"` |
