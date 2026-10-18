import os
from pathlib import Path

import dotenv
import pytest

import maos.config
from conftest import FAKE_API_KEY
from maos.config import PLACEHOLDER_API_KEY, ConfigError, load_settings


def test_missing_key_raises():
    with pytest.raises(ConfigError, match="OPENAI_API_KEY is not set"):
        load_settings()


def test_blank_key_raises(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    with pytest.raises(ConfigError):
        load_settings()


def test_placeholder_key_raises(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", PLACEHOLDER_API_KEY)
    with pytest.raises(ConfigError, match="placeholder"):
        load_settings()


def test_loads_key_and_default_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    settings = load_settings()
    assert settings.openai_api_key == FAKE_API_KEY
    assert settings.research_model is None


def test_loads_model_override(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("MAOS_RESEARCH_MODEL", " my-model ")
    assert load_settings().research_model == "my-model"


def test_key_not_in_repr(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    assert FAKE_API_KEY not in repr(load_settings())


# .env lookup and precedence. Each test writes a throwaway .env with a fake
# key under tmp_path; no real .env or key is ever read.

OTHER_FAKE_KEY = "sk-test-OTHER-FAKE-KEY-1111111111111"
BLANK_VALUES = ["", "   ", "\t \n"]


@pytest.fixture
def real_dotenv_lookup(monkeypatch, tmp_path):
    """Restore the real .env lookup and run from an empty temporary directory."""
    monkeypatch.setattr(maos.config, "find_dotenv", dotenv.find_dotenv)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_env(directory, key=FAKE_API_KEY, model="dotenv-model"):
    path = directory / ".env"
    path.write_text(f"OPENAI_API_KEY={key}\nMAOS_RESEARCH_MODEL={model}\n")
    return path


def test_dotenv_in_working_directory_is_used(real_dotenv_lookup):
    _write_env(real_dotenv_lookup)
    settings = load_settings()
    assert settings.openai_api_key == FAKE_API_KEY
    assert settings.research_model == "dotenv-model"


def test_dotenv_in_parent_of_working_directory_is_used(monkeypatch, real_dotenv_lookup):
    _write_env(real_dotenv_lookup)
    nested = real_dotenv_lookup / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert load_settings().openai_api_key == FAKE_API_KEY


def test_dotenv_lookup_follows_working_directory(monkeypatch, real_dotenv_lookup):
    first = real_dotenv_lookup / "first"
    second = real_dotenv_lookup / "second"
    first.mkdir()
    second.mkdir()
    _write_env(first, key=FAKE_API_KEY)
    _write_env(second, key=OTHER_FAKE_KEY)

    monkeypatch.chdir(first)
    assert load_settings().openai_api_key == FAKE_API_KEY
    monkeypatch.chdir(second)
    assert load_settings().openai_api_key == OTHER_FAKE_KEY


def test_dotenv_lookup_starts_from_working_directory(monkeypatch):
    """Independent of install layout: the search must not start at config.py."""
    calls = []

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return ""

    monkeypatch.setattr(maos.config, "find_dotenv", spy)
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    load_settings()
    assert calls == [((), {"usecwd": True})]


def test_loading_dotenv_does_not_modify_environment(real_dotenv_lookup):
    _write_env(real_dotenv_lookup)
    load_settings()
    assert "OPENAI_API_KEY" not in os.environ
    assert "MAOS_RESEARCH_MODEL" not in os.environ


@pytest.mark.parametrize("blank", BLANK_VALUES, ids=["empty", "spaces", "mixed"])
def test_blank_environment_key_falls_back_to_dotenv(monkeypatch, real_dotenv_lookup, blank):
    _write_env(real_dotenv_lookup)
    monkeypatch.setenv("OPENAI_API_KEY", blank)
    assert load_settings().openai_api_key == FAKE_API_KEY


@pytest.mark.parametrize("blank", BLANK_VALUES, ids=["empty", "spaces", "mixed"])
def test_blank_environment_model_falls_back_to_dotenv(monkeypatch, real_dotenv_lookup, blank):
    _write_env(real_dotenv_lookup)
    monkeypatch.setenv("MAOS_RESEARCH_MODEL", blank)
    assert load_settings().research_model == "dotenv-model"


def test_non_empty_environment_values_take_precedence(monkeypatch, real_dotenv_lookup):
    _write_env(real_dotenv_lookup)
    monkeypatch.setenv("OPENAI_API_KEY", f"  {OTHER_FAKE_KEY}  ")
    monkeypatch.setenv("MAOS_RESEARCH_MODEL", " env-model ")
    settings = load_settings()
    assert settings.openai_api_key == OTHER_FAKE_KEY
    assert settings.research_model == "env-model"


@pytest.mark.parametrize("blank", BLANK_VALUES, ids=["empty", "spaces", "mixed"])
def test_blank_in_environment_and_dotenv_is_unset(monkeypatch, real_dotenv_lookup, blank):
    (real_dotenv_lookup / ".env").write_text(
        f'OPENAI_API_KEY="{blank}"\nMAOS_RESEARCH_MODEL="{blank}"\n'
    )
    monkeypatch.setenv("OPENAI_API_KEY", blank)
    monkeypatch.setenv("MAOS_RESEARCH_MODEL", blank)
    with pytest.raises(ConfigError, match="OPENAI_API_KEY is not set"):
        load_settings()

    monkeypatch.setenv("OPENAI_API_KEY", FAKE_API_KEY)
    assert load_settings().research_model is None


def test_placeholder_key_in_dotenv_raises(real_dotenv_lookup):
    _write_env(real_dotenv_lookup, key=PLACEHOLDER_API_KEY)
    with pytest.raises(ConfigError, match="placeholder"):
        load_settings()


def test_example_file_has_placeholders_only(real_dotenv_lookup):
    """The shipped .env.example, used as .env, must not yield a usable key."""
    example = Path(__file__).resolve().parents[1] / ".env.example"
    (real_dotenv_lookup / ".env").write_text(example.read_text())
    with pytest.raises(ConfigError, match="placeholder"):
        load_settings()
