"""Prove that the offline safety net in conftest.py actually triggers."""

import asyncio
import socket

import pytest
from agents import Runner

from conftest import NetworkAccessError
from maos.agents.research_agent import build_research_agent


def test_outbound_connection_is_blocked():
    with pytest.raises(NetworkAccessError):
        socket.create_connection(("api.openai.com", 443), timeout=1)


def test_raw_socket_connect_is_blocked():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(NetworkAccessError):
            sock.connect(("127.0.0.1", 9))


def test_dns_lookup_is_blocked():
    with pytest.raises(NetworkAccessError):
        socket.getaddrinfo("api.openai.com", 443)


def test_real_runner_run_sync_is_blocked():
    with pytest.raises(AssertionError, match="Real Runner.run_sync"):
        Runner.run_sync(build_research_agent(), "test")


def test_real_runner_run_is_blocked():
    with pytest.raises(AssertionError, match="Real Runner.run"):
        asyncio.run(Runner.run(build_research_agent(), "test"))
