"""Command-line entry point for the MAOS Research Agent."""

import argparse
import logging
import sys

from agents import set_default_openai_key

from maos import __version__
from maos.agents.research_agent import run_research
from maos.config import ConfigError, load_settings
from maos.errors import describe_run_error

EXIT_OK = 0
EXIT_RUN_ERROR = 1
EXIT_CONFIG_ERROR = 2
EXIT_INTERRUPTED = 130

# SDK loggers whose records can include raw OpenAI error text.
SDK_LOGGERS = ("openai", "openai.agents")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maos-research",
        description=(
            "Run the MAOS Research Agent (V1.1). No live search is performed; "
            "output is based on model knowledge only."
        ),
    )
    add_request_arguments(parser)
    return parser


def add_request_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the request arguments shared by the MAOS commands."""
    parser.add_argument("request", help="the research request")
    parser.add_argument("--subject", help="company or market name")
    parser.add_argument("--topic", help="research topic")
    parser.add_argument("--period", help="relevant time period")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )


def silence_sdk_logging() -> None:
    """Keep SDK log records off stderr.

    The SDK logs failed model calls before re-raising them, and with no
    handler configured Python's last-resort handler prints them to stderr.
    With OPENAI_AGENTS_DONT_LOG_MODEL_DATA=0 those records include the
    OpenAI error message, which can echo part of the key.
    """
    for name in SDK_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(h, logging.NullHandler) for h in logger.handlers):
            logger.addHandler(logging.NullHandler())
        logger.propagate = False


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

    # run_research() disables tracing before the SDK run.
    try:
        output = run_research(
            args.request,
            subject=args.subject,
            topic=args.topic,
            period=args.period,
            model=settings.research_model,
        )
    except KeyboardInterrupt:
        _error("interrupted.")
        return EXIT_INTERRUPTED
    except Exception as exc:
        _error(describe_run_error(exc))
        return EXIT_RUN_ERROR

    print(output)
    return EXIT_OK
