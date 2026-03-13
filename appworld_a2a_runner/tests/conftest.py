"""Shared fixtures for AppWorld A2A Runner tests."""

import pytest

from appworld_a2a_runner.config import A2AConfig


@pytest.fixture()
def a2a_config():
    """Minimal A2AConfig for unit tests."""
    return A2AConfig(
        base_url="http://localhost:8000",
        timeout_seconds=30,
        auth_token=None,
        verify_tls=False,
        endpoint_path="/v1/chat",
    )
