import pytest

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
