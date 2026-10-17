"""Shared fixtures that keep every test offline and key-free."""

import socket

import pytest
from agents import Runner, set_tracing_disabled

import maos.config

FAKE_API_KEY = "sk-test-FAKE-KEY-0000000000000000"


class NetworkAccessError(AssertionError):
    """Raised when a test attempts a real network connection."""


def _block_network(*args, **kwargs):
    raise NetworkAccessError("Network access attempted during offline tests")


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    """Isolate tests from the real environment, any local .env, and the API."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MAOS_RESEARCH_MODEL", raising=False)
    monkeypatch.setattr(maos.config, "load_dotenv", lambda *a, **k: False)

    # Socket-level guard: DNS lookups and outbound connections fail loudly.
    monkeypatch.setattr(socket.socket, "connect", _block_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _block_network)
    monkeypatch.setattr(socket, "create_connection", _block_network)
    monkeypatch.setattr(socket, "getaddrinfo", _block_network)

    def _blocked_run_sync(*args, **kwargs):
        raise AssertionError("Real Runner.run_sync called during offline tests")

    async def _blocked_run(*args, **kwargs):
        raise AssertionError("Real Runner.run called during offline tests")

    monkeypatch.setattr(Runner, "run_sync", _blocked_run_sync)
    monkeypatch.setattr(Runner, "run", _blocked_run)

    set_tracing_disabled(True)
