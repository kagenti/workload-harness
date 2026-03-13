"""Tests for configuration management."""

import pytest

from appworld_a2a_runner.config import (
    A2AConfig,
    AppWorldConfig,
    DebugConfig,
    OTELConfig,
    _get_bool,
    _get_int,
)


class TestGetBool:
    """Tests for _get_bool helper."""

    def test_true_values(self, monkeypatch):
        for val in ("1", "true", "True", "TRUE", "yes", "Yes", "on", "ON"):
            monkeypatch.setenv("TEST_BOOL", val)
            assert _get_bool("TEST_BOOL") is True

    def test_false_values(self, monkeypatch):
        for val in ("0", "false", "False", "FALSE", "no", "No", "off", "OFF"):
            monkeypatch.setenv("TEST_BOOL", val)
            assert _get_bool("TEST_BOOL") is False

    def test_unset_returns_default(self, monkeypatch):
        monkeypatch.delenv("TEST_BOOL", raising=False)
        assert _get_bool("TEST_BOOL") is False
        assert _get_bool("TEST_BOOL", True) is True

    def test_unrecognized_value_returns_default(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "maybe")
        assert _get_bool("TEST_BOOL") is False
        assert _get_bool("TEST_BOOL", True) is True


class TestGetInt:
    """Tests for _get_int helper."""

    def test_valid_int(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "42")
        assert _get_int("TEST_INT") == 42

    def test_negative_int(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "-5")
        assert _get_int("TEST_INT") == -5

    def test_unset_returns_default(self, monkeypatch):
        monkeypatch.delenv("TEST_INT", raising=False)
        assert _get_int("TEST_INT") is None
        assert _get_int("TEST_INT", 10) == 10

    def test_invalid_value_returns_default(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "abc")
        assert _get_int("TEST_INT") is None
        assert _get_int("TEST_INT", 99) == 99


class TestA2AConfig:
    """Tests for A2AConfig.from_env."""

    def test_from_env_required_fields(self, monkeypatch):
        monkeypatch.setenv("A2A_BASE_URL", "http://agent:8080")
        monkeypatch.delenv("A2A_TIMEOUT_SECONDS", raising=False)
        monkeypatch.delenv("A2A_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("A2A_VERIFY_TLS", raising=False)
        monkeypatch.delenv("A2A_ENDPOINT_PATH", raising=False)

        config = A2AConfig.from_env()
        assert config.base_url == "http://agent:8080"
        assert config.timeout_seconds == 300
        assert config.auth_token is None
        assert config.verify_tls is True
        assert config.endpoint_path == "/v1/chat"

    def test_from_env_all_overrides(self, monkeypatch):
        monkeypatch.setenv("A2A_BASE_URL", "https://prod:443")
        monkeypatch.setenv("A2A_TIMEOUT_SECONDS", "60")
        monkeypatch.setenv("A2A_AUTH_TOKEN", "secret-token")
        monkeypatch.setenv("A2A_VERIFY_TLS", "false")
        monkeypatch.setenv("A2A_ENDPOINT_PATH", "/rpc")

        config = A2AConfig.from_env()
        assert config.base_url == "https://prod:443"
        assert config.timeout_seconds == 60
        assert config.auth_token == "secret-token"
        assert config.verify_tls is False
        assert config.endpoint_path == "/rpc"

    def test_from_env_missing_base_url_raises(self, monkeypatch):
        monkeypatch.delenv("A2A_BASE_URL", raising=False)
        with pytest.raises(ValueError, match="A2A_BASE_URL"):
            A2AConfig.from_env()


class TestAppWorldConfig:
    """Tests for AppWorldConfig.from_env."""

    def test_from_env_required_fields(self, monkeypatch):
        monkeypatch.setenv("APPWORLD_DATASET", "test_normal")
        monkeypatch.setenv("APPWORLD_REMOTE_APIS_URL", "http://apis:8080")
        monkeypatch.delenv("APPWORLD_ROOT", raising=False)
        monkeypatch.delenv("MAX_TASKS", raising=False)
        monkeypatch.delenv("ABORT_ON_FAILURE", raising=False)

        config = AppWorldConfig.from_env()
        assert config.dataset == "test_normal"
        assert config.remote_apis_url == "http://apis:8080"
        assert config.root is None
        assert config.max_tasks is None
        assert config.abort_on_failure is False

    def test_from_env_missing_dataset_raises(self, monkeypatch):
        monkeypatch.delenv("APPWORLD_DATASET", raising=False)
        monkeypatch.delenv("APPWORLD_REMOTE_APIS_URL", raising=False)
        with pytest.raises(ValueError, match="APPWORLD_DATASET"):
            AppWorldConfig.from_env()

    def test_from_env_missing_remote_apis_url_raises(self, monkeypatch):
        monkeypatch.setenv("APPWORLD_DATASET", "test_normal")
        monkeypatch.delenv("APPWORLD_REMOTE_APIS_URL", raising=False)
        with pytest.raises(ValueError, match="APPWORLD_REMOTE_APIS_URL"):
            AppWorldConfig.from_env()


class TestOTELConfig:
    """Tests for OTELConfig.from_env."""

    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_PROTOCOL", raising=False)
        monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)
        monkeypatch.delenv("OTEL_INSTRUMENT_REQUESTS", raising=False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_INSECURE", raising=False)

        config = OTELConfig.from_env()
        assert config.service_name == "appworld-a2a-proxy"
        assert config.exporter_endpoint is None
        assert config.exporter_protocol == "grpc"
        assert config.instrument_requests is True
        assert config.exporter_insecure is True


class TestDebugConfig:
    """Tests for DebugConfig.from_env."""

    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("LOG_PROMPT", raising=False)
        monkeypatch.delenv("LOG_RESPONSE", raising=False)

        config = DebugConfig.from_env()
        assert config.log_prompt is False
        assert config.log_response is False

    def test_enabled(self, monkeypatch):
        monkeypatch.setenv("LOG_PROMPT", "true")
        monkeypatch.setenv("LOG_RESPONSE", "1")

        config = DebugConfig.from_env()
        assert config.log_prompt is True
        assert config.log_response is True
