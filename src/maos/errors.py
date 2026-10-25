"""Safe, user-facing descriptions of MAOS run failures.

Shared by the CLIs, and usable by a future API layer, so every interface
reports failures the same way. Exception messages can echo part of the API
key, so only exception types and MAOS's own text are used.

Imports stay lightweight so maos-research does not load the workflow or the
Investment Analyst.
"""

from typing import TYPE_CHECKING

import openai
from agents.exceptions import AgentsException

from maos.agents.research_agent import EmptyResearchOutputError
from maos.contracts import EmptyAnalysisOutputError, OutputValidationError

if TYPE_CHECKING:
    from maos.workflow import WorkflowStageError


def describe_run_error(exc: BaseException | None) -> str:
    """Return a safe one-line description of a failed agent run."""
    if isinstance(exc, openai.AuthenticationError):
        return "OpenAI rejected the API key. Check OPENAI_API_KEY."
    if isinstance(exc, openai.RateLimitError):
        return "OpenAI rate limit or quota exceeded. Try again later."
    if isinstance(exc, openai.APIConnectionError):
        return "could not connect to the OpenAI API. Check your network."
    if isinstance(exc, openai.APIStatusError):
        return f"OpenAI API returned HTTP {exc.status_code}."
    if isinstance(exc, openai.OpenAIError):
        return f"OpenAI request failed ({type(exc).__name__})."
    if isinstance(exc, AgentsException):
        return f"agent run failed ({type(exc).__name__})."
    if isinstance(exc, (EmptyResearchOutputError, EmptyAnalysisOutputError)):
        return "the agent returned no output."
    if isinstance(exc, OutputValidationError):
        return f"the agent's output was invalid ({exc.summary()})."
    return f"unexpected error ({type(exc).__name__})."


def describe_stage_error(exc: "WorkflowStageError") -> str:
    """Return a safe one-line description naming the failed stage."""
    return f"{exc.stage} stage: {describe_run_error(exc.__cause__)}"
