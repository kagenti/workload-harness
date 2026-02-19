"""AppWorld A2A Proxy Runner.

A standalone Python runner that uses AppWorld to enumerate tasks and fetch task text,
then calls a remote agent over A2A with a plain-text prompt, collects the plain-text
response, and emits OpenTelemetry (OTEL) telemetry.
"""

__version__ = "0.1.0"

from .config import Config
from .runner import Runner

__all__ = ["Config", "Runner", "__version__"]

# Made with Bob
