"""Tests for A2A client helpers.

Tests URL normalization and response extraction without making network calls.
"""

from unittest.mock import patch

import pytest

from appworld_a2a_runner.a2a_client import A2AProxyClient
from appworld_a2a_runner.config import A2AConfig


def _make_client(base_url="http://localhost:8000", endpoint_path="/v1/chat"):
    """Create an A2AProxyClient with agent card fetch mocked out."""
    config = A2AConfig(
        base_url=base_url,
        timeout_seconds=30,
        verify_tls=False,
        endpoint_path=endpoint_path,
    )
    with patch.object(A2AProxyClient, "_discover_rpc_url", return_value=f"{base_url}{endpoint_path}"):
        return A2AProxyClient(config)


class TestNormalizeEndpointPath:
    """Tests for _normalize_endpoint_path."""

    def test_default_path(self):
        client = _make_client(endpoint_path="/v1/chat")
        assert client._normalize_endpoint_path() == "/v1/chat"

    def test_missing_leading_slash(self):
        client = _make_client(endpoint_path="rpc")
        assert client._normalize_endpoint_path() == "/rpc"

    def test_empty_string(self):
        client = _make_client(endpoint_path="")
        assert client._normalize_endpoint_path() == "/"

    def test_whitespace(self):
        client = _make_client(endpoint_path="  /api  ")
        assert client._normalize_endpoint_path() == "/api"


class TestBuildRpcUrl:
    """Tests for _build_rpc_url."""

    def test_strips_trailing_slash(self):
        client = _make_client(endpoint_path="/rpc")
        assert client._build_rpc_url("http://host:8000/") == "http://host:8000/rpc"

    def test_no_trailing_slash(self):
        client = _make_client(endpoint_path="/v1/chat")
        assert client._build_rpc_url("http://host:8000") == "http://host:8000/v1/chat"


class TestExtractTextFromMessage:
    """Tests for _extract_text_from_message."""

    def test_text_parts(self):
        client = _make_client()
        msg = {"parts": [{"kind": "text", "text": "Hello"}, {"kind": "text", "text": "World"}]}
        assert client._extract_text_from_message(msg) == "Hello\nWorld"

    def test_single_text_part(self):
        client = _make_client()
        msg = {"parts": [{"kind": "text", "text": "Response"}]}
        assert client._extract_text_from_message(msg) == "Response"

    def test_fallback_content_field(self):
        client = _make_client()
        msg = {"content": "fallback text"}
        assert client._extract_text_from_message(msg) == "fallback text"

    def test_no_extractable_text_raises(self):
        client = _make_client()
        with pytest.raises(ValueError, match="Could not extract text"):
            client._extract_text_from_message({})

    def test_skips_non_text_parts(self):
        client = _make_client()
        msg = {"parts": [{"kind": "image", "url": "http://img"}, {"kind": "text", "text": "Caption"}]}
        assert client._extract_text_from_message(msg) == "Caption"


class TestExtractTextFromTask:
    """Tests for _extract_text_from_task."""

    def test_failed_task_raises(self):
        client = _make_client()
        task = {"status": {"state": "failed", "error": "out of memory"}}
        with pytest.raises(ValueError, match="Task failed: out of memory"):
            client._extract_text_from_task(task)

    def test_canceled_task_raises(self):
        client = _make_client()
        task = {"status": {"state": "canceled"}}
        with pytest.raises(ValueError, match="canceled"):
            client._extract_text_from_task(task)

    def test_rejected_task_raises(self):
        client = _make_client()
        task = {"status": {"state": "rejected"}}
        with pytest.raises(ValueError, match="rejected"):
            client._extract_text_from_task(task)

    def test_artifact_extraction(self):
        client = _make_client()
        task = {
            "status": {"state": "completed"},
            "artifacts": [{"parts": [{"kind": "text", "text": "done"}]}],
        }
        assert client._extract_text_from_task(task) == "done"

    def test_result_message_extraction(self):
        client = _make_client()
        task = {
            "status": {"state": "completed"},
            "result": {"message": {"parts": [{"kind": "text", "text": "reply"}]}},
        }
        assert client._extract_text_from_task(task) == "reply"

    def test_result_text_field(self):
        client = _make_client()
        task = {
            "status": {"state": "completed"},
            "result": {"text": "plain result"},
        }
        assert client._extract_text_from_task(task) == "plain result"

    def test_result_string(self):
        client = _make_client()
        task = {
            "status": {"state": "completed"},
            "result": "raw string",
        }
        assert client._extract_text_from_task(task) == "raw string"

    def test_no_result_raises(self):
        client = _make_client()
        task = {"status": {"state": "completed"}}
        with pytest.raises(ValueError, match="Could not extract text"):
            client._extract_text_from_task(task)
