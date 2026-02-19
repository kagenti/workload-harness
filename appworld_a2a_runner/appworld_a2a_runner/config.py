"""Configuration management for AppWorld A2A Runner.

Configuration is loaded from environment variables with optional CLI overrides.
"""
import os
from dataclasses import dataclass
from typing import Optional


def _get_bool(key: str, default: bool = False) -> bool:
    """Get boolean value from environment variable."""
    value = os.getenv(key, "").lower()
    if value in ("1", "true", "yes", "on"):
        return True
    elif value in ("0", "false", "no", "off"):
        return False
    return default


def _get_int(key: str, default: Optional[int] = None) -> Optional[int]:
    """Get integer value from environment variable."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass
class A2AConfig:
    """A2A endpoint configuration."""
    
    base_url: str
    timeout_seconds: int = 300
    auth_token: Optional[str] = None
    verify_tls: bool = True
    endpoint_path: str = "/v1/chat"
    
    @classmethod
    def from_env(cls) -> "A2AConfig":
        """Load A2A configuration from environment variables."""
        base_url = os.getenv("A2A_BASE_URL")
        if not base_url:
            raise ValueError("A2A_BASE_URL environment variable is required")
        
        return cls(
            base_url=base_url,
            timeout_seconds=_get_int("A2A_TIMEOUT_SECONDS", 300) or 300,
            auth_token=os.getenv("A2A_AUTH_TOKEN"),
            verify_tls=_get_bool("A2A_VERIFY_TLS", True),
            endpoint_path=os.getenv("A2A_ENDPOINT_PATH", "/v1/chat"),
        )


@dataclass
class AppWorldConfig:
    """AppWorld dataset configuration."""
    
    dataset: str
    remote_apis_url: Optional[str] = None
    root: Optional[str] = None
    max_tasks: Optional[int] = None
    abort_on_failure: bool = False
    
    @classmethod
    def from_env(cls) -> "AppWorldConfig":
        """Load AppWorld configuration from environment variables."""
        dataset = os.getenv("APPWORLD_DATASET")
        if not dataset:
            raise ValueError("APPWORLD_DATASET environment variable is required")
        remote_apis_url = os.getenv("APPWORLD_REMOTE_APIS_URL")
        if not remote_apis_url:
            raise ValueError("APPWORLD_REMOTE_APIS_URL environment variable is required")
        
        return cls(
            dataset=dataset,
            remote_apis_url=remote_apis_url,
            root=os.getenv("APPWORLD_ROOT"),
            max_tasks=_get_int("MAX_TASKS"),
            abort_on_failure=_get_bool("ABORT_ON_FAILURE", False),
        )


@dataclass
class OTELConfig:
    """OpenTelemetry configuration."""
    
    service_name: str = "appworld-a2a-proxy"
    exporter_endpoint: Optional[str] = None
    exporter_protocol: str = "grpc"
    resource_attributes: Optional[str] = None
    instrument_requests: bool = True
    exporter_insecure: bool = True

    @classmethod
    def from_env(cls) -> "OTELConfig":
        """Load OTEL configuration from environment variables."""
        return cls(
            service_name=os.getenv("OTEL_SERVICE_NAME", "appworld-a2a-proxy"),
            exporter_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
            exporter_protocol=os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc"),
            resource_attributes=os.getenv("OTEL_RESOURCE_ATTRIBUTES"),
            instrument_requests=_get_bool("OTEL_INSTRUMENT_REQUESTS", True),
            exporter_insecure=_get_bool("OTEL_EXPORTER_OTLP_INSECURE", True),
        )


@dataclass
class DebugConfig:
    """Debug and logging configuration."""
    
    log_prompt: bool = False
    log_response: bool = False
    
    @classmethod
    def from_env(cls) -> "DebugConfig":
        """Load debug configuration from environment variables."""
        return cls(
            log_prompt=_get_bool("LOG_PROMPT", False),
            log_response=_get_bool("LOG_RESPONSE", False),
        )


@dataclass
class Config:
    """Complete runner configuration."""
    
    a2a: A2AConfig
    appworld: AppWorldConfig
    otel: OTELConfig
    debug: DebugConfig
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load complete configuration from environment variables."""
        return cls(
            a2a=A2AConfig.from_env(),
            appworld=AppWorldConfig.from_env(),
            otel=OTELConfig.from_env(),
            debug=DebugConfig.from_env(),
        )

# Made with Bob
