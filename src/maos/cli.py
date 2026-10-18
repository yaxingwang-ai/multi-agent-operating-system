"""Command-line entry point for the MAOS Research Agent."""

import argparse
import logging
import sys

import openai
from agents import set_default_openai_key
from agents.exceptions import AgentsException

from maos import __version__
from maos.agents.research_agent import EmptyResearchOutputError, run_research
from maos.config import ConfigError, load_settings

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
    parser.add_argument("request", help="the research request")
    parser.add_argument("--subject", help="company or market name")
    parser.add_argument("--topic", help="research topic")
    parser.add_argument("--period", help="relevant time period")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


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

    # Exception messages can echo part of the key, so only types are printed.
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
    except openai.AuthenticationError:
        _error("OpenAI rejected the API key. Check OPENAI_API_KEY.")
        return EXIT_RUN_ERROR
    except openai.RateLimitError:
        _error("OpenAI rate limit or quota exceeded. Try again later.")
        return EXIT_RUN_ERROR
    except openai.APIConnectionError:
        _error("could not connect to the OpenAI API. Check your network.")
        return EXIT_RUN_ERROR
    except openai.APIStatusError as exc:
        _error(f"OpenAI API returned HTTP {exc.status_code}.")
        return EXIT_RUN_ERROR
    except openai.OpenAIError as exc:
        _error(f"OpenAI request failed ({type(exc).__name__}).")
        return EXIT_RUN_ERROR
    except AgentsException as exc:
        _error(f"agent run failed ({type(exc).__name__}).")
        return EXIT_RUN_ERROR
    except EmptyResearchOutputError:
        _error("the agent returned no output.")
        return EXIT_RUN_ERROR
    except Exception as exc:
        _error(f"unexpected error ({type(exc).__name__}).")
        return EXIT_RUN_ERROR

    print(output)
    return EXIT_OK
