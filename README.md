# Multi-Agent Operating System

> A modular AI Operating System for autonomous AI agent orchestration.

---

## 🎯 Project Vision

Multi-Agent Operating System (MAOS) is a personal AI engineering project focused on building a modular operating system where multiple AI agents collaborate to solve complex tasks.

Rather than creating a single AI assistant, MAOS provides a reusable architecture that supports different AI-powered applications.

The first application built on this platform is **AI Investment Company**, an autonomous investment research system designed to automate research, analysis, reporting and investment decision support.

---

## 🚀 Current Development Stage

Current Version: **V1.2 – Multi-Agent Workflow**

- **V1.0** (tagged `v1.0.0`): system architecture and agent specifications
- **V1.1**: the Research Agent runs from the command line
- **V1.2**: the Research Agent and Investment Analyst run as one workflow
- **Next:** V1.3 – Tools and APIs (planned)

Status: 🟢 Active Development

---

## 📌 Project Goals

- Build a reusable Multi-Agent Operating System
- Design specialised AI agents with clear responsibilities
- Develop autonomous investment research workflows
- Integrate Python automation and AI APIs
- Deploy a production-ready AI engineering portfolio

---

## 🏗️ System Architecture

```mermaid
graph TD

User --> MAOS["Multi-Agent Operating System"]

MAOS --> Research["Research Agent"]
MAOS --> Analysis["Investment Analyst"]
MAOS --> Risk["Risk Manager"]
MAOS --> Portfolio["Portfolio Manager"]

Research --> Knowledge["Knowledge & Memory Layer"]
Analysis --> Knowledge
Risk --> Knowledge
Portfolio --> Knowledge

Knowledge --> Application["AI Investment Company"]

Application --> Dashboard["Investment Dashboard"]
```

This diagram shows the target architecture. The Research Agent and
Investment Analyst are implemented so far; the other components are planned.

The V1.2 workflow:

```mermaid
graph LR
Request["User Request"] --> Research["Research Agent"]
Research --> V1["Validate sections"]
V1 --> Analyst["Investment Analyst"]
Analyst --> V2["Validate sections"]
V2 --> Report["Final Report"]
```

---

## 🤖 AI Agents

Each agent has a written specification (system prompt) in
[`docs/prompts/`](docs/prompts/), created in V1.0.

| Agent | Specification | Status |
|---|---|---|
| Research Agent | [research-agent.md](docs/prompts/research-agent.md) | ✅ Executable (V1.1) |
| Investment Analyst | [investment-analyst.md](docs/prompts/investment-analyst.md) | ✅ Executable (V1.2) |
| Risk Manager | [risk-manager.md](docs/prompts/risk-manager.md) | Specification only |
| Portfolio Manager | [portfolio-manager.md](docs/prompts/portfolio-manager.md) | Specification only |
| Market Monitor | [market-monitor.md](docs/prompts/market-monitor.md) | Specification only |
| Report Generator | [report-generator.md](docs/prompts/report-generator.md) | Specification only |

---

## 📈 Applications

### AI Investment Company

You give MAOS a research request (optionally a company or market, topic,
and time period).

- `maos-research` (V1.1) runs the **Research Agent** alone and returns a
  structured Markdown report that separates facts from interpretations.
- `maos-workflow` (V1.2) passes that research to the **Investment Analyst**,
  checks each agent's output has the required sections, and returns one
  combined report.

> **Limitation:** MAOS has no live web search or market data. The agents
> answer from model knowledge only, which may be out of date, and any
> sources they list are unverified suggestions. The Investment Analyst is
> instructed not to give buy, sell, or hold recommendations, but this is a
> prompt instruction, not a guarantee. **Nothing MAOS produces is investment
> advice.** Do not use its output as current market data or to make
> investment decisions.

---

## 🛠️ Technology Stack

**Requirements:** Python 3.10 or later, and an OpenAI API key to run the agent.

**Runtime dependencies** (installed with the package):

- [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) (`openai-agents` 0.23.1)
- OpenAI Python SDK (`openai` 3.33.0)
- `python-dotenv` 1.2.4, for loading the API key from a local `.env` file

**Development dependencies** (installed with the `dev` extra):

- `pytest` 9.1.1, for the offline test suite

All versions are pinned in [`pyproject.toml`](pyproject.toml).

---

## ⚡ Quick Start

Check your Python version first with `python3 --version`. It must be 3.10
or later. The `python3` that ships with macOS may be older; if so, install a
newer Python from [python.org](https://www.python.org/downloads/) or
Homebrew.

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]" -c constraints.txt

cp .env.example .env   # then put your OpenAI API key in .env

maos-research "Give an overview of the global semiconductor industry"
maos-workflow "Give an overview of the global semiconductor industry"
```

Each run makes real API calls and uses API credit. A successful run makes
one model call for `maos-research` and two for `maos-workflow`; the SDK
retries some failed requests automatically, so the number of HTTP requests
can be higher. To run the offline tests (no API key or network needed), run
`pytest`.

See the [Research Agent Setup Guide](docs/v1.1/research-agent-setup.md)
for configuration, all command options, API key safety, and
troubleshooting, and the [Multi-Agent Workflow Guide](docs/v1.2/multi-agent-workflow.md)
for the V1.2 workflow, its data contracts, and failure handling.

---

## 🗺️ Roadmap

| Version | Focus | Status |
|---|---|---|
| V1.1 | First executable Research Agent | ✅ Done |
| V1.2 | Multi-Agent Workflow | ✅ Done |
| V1.3 | Tools and APIs | Planned |
| V1.4 | MCP | Planned |
