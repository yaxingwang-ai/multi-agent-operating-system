"""Shared fixtures that keep every test offline and key-free."""

import logging
import socket

import pytest
from agents import Runner, set_tracing_disabled

import maos.config

FAKE_API_KEY = "sk-test-FAKE-KEY-0000000000000000"

# The real classmethod, saved before any test replaces it.
REAL_RUN_SYNC = Runner.__dict__["run_sync"]

SDK_LOGGER_NAMES = ("openai", "openai.agents")


class NetworkAccessError(AssertionError):
    """Raised when a test attempts a real network connection."""


def _block_network(*args, **kwargs):
    raise NetworkAccessError("Network access attempted during offline tests")


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    """Isolate tests from the real environment, any local .env, and the API."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MAOS_RESEARCH_MODEL", raising=False)
    # No .env is found unless a test restores the real lookup.
    monkeypatch.setattr(maos.config, "find_dotenv", lambda *a, **k: "")

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


@pytest.fixture(autouse=True)
def restore_sdk_loggers():
    """Undo the CLI's SDK logger changes so each test starts clean."""
    loggers = [logging.getLogger(name) for name in SDK_LOGGER_NAMES]
    saved = [(lg.handlers[:], lg.propagate) for lg in loggers]
    yield
    for lg, (handlers, propagate) in zip(loggers, saved):
        lg.handlers[:] = handlers
        lg.propagate = propagate
