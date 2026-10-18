"""Environment configuration for MAOS.

Secrets are read from the environment, falling back to a local, git-ignored
.env file. Key values are never included in messages or reprs.
"""

import os
from dataclasses import dataclass, field

from dotenv import dotenv_values, find_dotenv

API_KEY_VAR = "OPENAI_API_KEY"
MODEL_VAR = "MAOS_RESEARCH_MODEL"
PLACEHOLDER_API_KEY = "your-openai-api-key-here"


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = field(repr=False)
    research_model: str | None = None


def _read_dotenv() -> dict[str, str | None]:
    """Read the nearest .env, searching upward from the working directory.

    The search starts from the working directory, not this file, so it works
    for both editable and regular installs. os.environ is not modified.
    """
    path = find_dotenv(usecwd=True)
    return dotenv_values(path) if path else {}


def _resolve(name: str, dotenv: dict[str, str | None]) -> str:
    """Return a non-blank environment value, else the .env value, else ""."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    return (dotenv.get(name) or "").strip()


def load_settings() -> Settings:
    """Load settings from the environment and an optional .env file.

    Non-blank environment values take precedence over .env. A variable that
    is unset, empty, or whitespace-only in the environment falls back to .env.
    """
    dotenv = _read_dotenv()

    api_key = _resolve(API_KEY_VAR, dotenv)
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

    model = _resolve(MODEL_VAR, dotenv) or None
    return Settings(openai_api_key=api_key, research_model=model)
