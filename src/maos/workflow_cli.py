"""Command-line entry point for the MAOS Multi-Agent Workflow (V1.2)."""

import argparse
import sys

from agents import set_default_openai_key

from maos.cli import (
    EXIT_CONFIG_ERROR,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_RUN_ERROR,
    add_request_arguments,
    silence_sdk_logging,
)
from maos.config import ConfigError, load_settings
from maos.contracts import WorkflowRequest
from maos.errors import describe_run_error, describe_stage_error
from maos.workflow import WorkflowStageError, run_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maos-workflow",
        description=(
            "Run the MAOS Multi-Agent Workflow (V1.2): Research Agent, then "
            "Investment Analyst. No live search is performed; output is based on "
            "model knowledge only and is not investment advice."
        ),
    )
    add_request_arguments(parser)
    return parser


def _error(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.request.strip():
        parser.error("request must not be empty")

    try:
        settings = load_settings()
    except ConfigError as exc:
        _error(str(exc))
        return EXIT_CONFIG_ERROR

    set_default_openai_key(settings.openai_api_key, use_for_tracing=False)
    silence_sdk_logging()

    request = WorkflowRequest(
        request=args.request, subject=args.subject, topic=args.topic, period=args.period
    )
    # Both agents use MAOS_RESEARCH_MODEL, and disable tracing before each run.
    try:
        result = run_workflow(request, model=settings.research_model)
    except KeyboardInterrupt:
        _error("interrupted.")
        return EXIT_INTERRUPTED
    except WorkflowStageError as exc:
        _error(describe_stage_error(exc))
        return EXIT_RUN_ERROR
    except Exception as exc:
        _error(describe_run_error(exc))
        return EXIT_RUN_ERROR

    print(result.report_markdown, end="")
    return EXIT_OK
