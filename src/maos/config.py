"""Environment configuration for MAOS.

Secrets are read from the environment (optionally populated from a local,
git-ignored .env file). Key values are never included in messages or reprs.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

API_KEY_VAR = "OPENAI_API_KEY"
MODEL_VAR = "MAOS_RESEARCH_MODEL"
PLACEHOLDER_API_KEY = "your-openai-api-key-here"


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = field(repr=False)
    research_model: str | None = None


def load_settings() -> Settings:
    """Load settings from the environment and an optional .env file.

    Values already set in the environment take precedence over .env.
    """
    load_dotenv(override=False)

    api_key = os.environ.get(API_KEY_VAR, "").strip()
    if not api_key:
        raise ConfigError(
            f"{API_KEY_VAR} is not set. Copy .env.example to .env and add your "
            "key, or export it in your shell."
        )
    if api_key == PLACEHOLDER_API_KEY:
        raise ConfigError(
            f"{API_KEY_VAR} still contains the placeholder from .env.example. "
            "Replace it with your own key in .env."
        )

    model = os.environ.get(MODEL_VAR, "").strip() or None
    return Settings(openai_api_key=api_key, research_model=model)
