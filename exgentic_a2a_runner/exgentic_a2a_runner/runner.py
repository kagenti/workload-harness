"""Main runner for Exgentic A2A Runner.

Orchestrates session creation, A2A calls, evaluation, and telemetry collection.
"""

import argparse
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from .a2a_client import A2AProxyClient
from .config import Config
from .exgentic_adapter import ExgenticAdapter, SessionData
from .otel import OTELInstrumentation
from .prompt import build_prompt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Suppress verbose logs from third-party libraries
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("mcp.client.streamable_http").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)


class SessionResult:
    """Result of a single session execution."""

    def __init__(
        self,
        session_id: str,
        success: bool,
        latency_seconds: float,
        evaluation_result: bool,
        error: Optional[str] = None,
        response_chars: Optional[int] = None,
    ):
        self.session_id = session_id
        self.success = success
        self.latency_seconds = latency_seconds
        self.evaluation_result = evaluation_result
        self.error = error
        self.response_chars = response_chars


class RunSummary:
    """Summary of the entire run."""

    def __init__(self):
        self.start_time = time.time()
        self.results: List[SessionResult] = []
        self._lock = threading.Lock()

    def add_result(self, result: SessionResult) -> None:
        """Add a session result (thread-safe)."""
        with self._lock:
            self.results.append(result)

    def get_summary(self) -> dict:
        """Get summary statistics."""
        total_time = time.time() - self.start_time
        attempted = len(self.results)
        succeeded = sum(1 for r in self.results if r.success)
        failed = attempted - succeeded
        
        # Calculate evaluation success rate
        evaluated = sum(1 for r in self.results if r.success)
        eval_succeeded = sum(1 for r in self.results if r.success and r.evaluation_result)
        eval_success_rate = (eval_succeeded / evaluated * 100) if evaluated > 0 else 0

        latencies = [r.latency_seconds for r in self.results]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        # Calculate percentiles
        sorted_latencies = sorted(latencies)
        p50 = sorted_latencies[len(sorted_latencies) // 2] if sorted_latencies else 0
        p95_idx = min(int(len(sorted_latencies) * 0.95), len(sorted_latencies) - 1)
        p95 = sorted_latencies[p95_idx] if sorted_latencies else 0

        return {
            "sessions_attempted": attempted,
            "sessions_succeeded": succeeded,
            "sessions_failed": failed,
            "evaluation_success_rate": eval_success_rate,
            "total_wall_time_seconds": total_time,
            "average_latency_seconds": avg_latency,
            "p50_latency_seconds": p50,
            "p95_latency_seconds": p95,
        }

    def print_summary(self, max_parallel_sessions: int = 1) -> None:
        """Print summary to console.
        
        Args:
            max_parallel_sessions: Maximum number of parallel sessions configured
        """
        summary = self.get_summary()

        print("\n" + "=" * 60)
        print("RUN SUMMARY")
        print("=" * 60)
        print(f"Max Parallel Sessions: {max_parallel_sessions}")
        print(f"Sessions Attempted:   {summary['sessions_attempted']}")
        print(f"Sessions Succeeded:   {summary['sessions_succeeded']}")
        print(f"Sessions Failed:      {summary['sessions_failed']}")
        print(f"Evaluation Success:   {summary['evaluation_success_rate']:.1f}%")
        print(f"Total Wall Time:      {summary['total_wall_time_seconds']:.2f}s")
        print(f"Average Latency:      {summary['average_latency_seconds']:.2f}s")
        print(f"P50 Latency:          {summary['p50_latency_seconds']:.2f}s")
        print(f"P95 Latency:          {summary['p95_latency_seconds']:.2f}s")
        print("=" * 60)
        
        # Print error table if there are any failures
        failed_results = [r for r in self.results if not r.success and r.error]
        if failed_results:
            print("\nFAILED SESSIONS")
            print("=" * 60)
            print(f"{'Session ID':<40} {'Error':<20}")
            print("-" * 60)
            for result in failed_results:
                # Truncate error message if too long
                error = result.error or "Unknown error"
                error_msg = error[:100] + "..." if len(error) > 100 else error
                print(f"{result.session_id:<40} {error_msg:<20}")
            print("=" * 60)
        
        print()


class Runner:
    """Main runner orchestrating session execution."""

    def __init__(self, config: Config):
        """Initialize runner.

        Args:
            config: Complete configuration
        """
        self.config = config
        self.exgentic = ExgenticAdapter(config.exgentic)
        self.a2a_client = A2AProxyClient(config.a2a)
        self.otel = OTELInstrumentation(config.otel)
        self.summary = RunSummary()
        self.max_parallel_sessions = config.exgentic.max_parallel_sessions

    def initialize(self) -> None:
        """Initialize all components."""
        logger.info("Initializing runner components")
        self.otel.initialize()
        self.exgentic.initialize()
        logger.info("Runner initialization complete")

    def process_session(self, session_data: SessionData) -> SessionResult:
        """Process a single session.

        Follows the execution model from GitHub issue #963:
        1. Create session (already done)
        2. Build prompt with session_id
        3. Send to agent via A2A
        4. Evaluate session
        5. Close session
        6. Record statistics

        Args:
            session_data: Session data from Exgentic

        Returns:
            SessionResult with execution details
        """
        session_id = session_data.session_id
        start_time = time.time()

        logger.info(f"Processing session: {session_id}")

        # Start OTEL span
        with self.otel.session_span(
            session_id=session_id,
            mcp_server_url=self.config.exgentic.mcp_server_url,
            a2a_base_url=self.config.a2a.base_url,
            a2a_timeout=self.config.a2a.timeout_seconds,
        ) as span:
            try:
                # Build prompt with session_id and context
                with self.otel.child_span("exgentic_a2a.prompt.build") as prompt_span:
                    prompt = build_prompt(session_data.task, session_data.session_id, session_data.context)
                    # Record prompt on the build span
                    self.otel.record_prompt(prompt_span, prompt)
                
                # Also record on parent span for backward compatibility
                self.otel.record_prompt(span, prompt)

                if self.config.debug.log_prompt:
                    logger.debug(f"Prompt length: {len(prompt)} chars")

                # Send A2A request
                a2a_start = time.time()
                with self.otel.child_span("exgentic_a2a.a2a.send_prompt") as a2a_span:
                    response = self.a2a_client.send_prompt(prompt)
                    a2a_duration_seconds = time.time() - a2a_start
                    # Record prompt and response on the send span
                    a2a_span.set_attribute("prompt.chars", len(prompt))
                    a2a_span.set_attribute("prompt.text", prompt)
                    self.otel.record_response(a2a_span, response)
                    self.otel.record_a2a_request(a2a_span, a2a_duration_seconds)

                # Also record on parent span for backward compatibility
                self.otel.record_a2a_request(span, a2a_duration_seconds)
                self.otel.record_response(span, response)

                if self.config.debug.log_response:
                    logger.debug(f"Response length: {len(response)} chars")

                # Evaluate session
                eval_start = time.time()
                with self.otel.child_span("exgentic_a2a.mcp.evaluate_session") as eval_span:
                    evaluation_result = self.exgentic.evaluate_session(session_id)
                    eval_duration_seconds = time.time() - eval_start
                    # Record evaluation result on the evaluate span
                    eval_span.set_attribute("exgentic.evaluation_result", evaluation_result)
                    eval_span.set_attribute("exgentic.evaluation_duration_seconds", eval_duration_seconds)
                    if self.otel.evaluation_latency_histogram:
                        self.otel.evaluation_latency_histogram.record(eval_duration_seconds)
                
                # Also record on parent span for backward compatibility
                self.otel.record_evaluation(span, eval_duration_seconds)

                # Delete session
                with self.otel.child_span("exgentic_a2a.mcp.delete_session"):
                    self.exgentic.delete_session(session_id)

                # Record success
                self.otel.record_success(span, evaluation_result)

                latency_seconds = time.time() - start_time
                logger.info(
                    f"Session {session_id} completed in {latency_seconds:.2f}s "
                    f"(evaluation: {'success' if evaluation_result else 'failed'})"
                )

                return SessionResult(
                    session_id=session_id,
                    success=True,
                    latency_seconds=latency_seconds,
                    evaluation_result=evaluation_result,
                    response_chars=len(response),
                )

            except Exception as e:
                # Classify error type
                error_type = type(e).__name__
                error_msg = str(e)

                logger.error(f"Session {session_id} failed: {error_type}: {error_msg}")

                # Try to delete session even on failure
                try:
                    with self.otel.child_span("exgentic_a2a.mcp.delete_session"):
                        self.exgentic.delete_session(session_id)
                except Exception as delete_error:
                    logger.warning(f"Failed to delete session {session_id}: {delete_error}")

                # Record failure
                self.otel.record_failure(span, e, error_type)

                latency_seconds = time.time() - start_time

                return SessionResult(
                    session_id=session_id,
                    success=False,
                    latency_seconds=latency_seconds,
                    evaluation_result=False,
                    error=f"{error_type}: {error_msg}",
                )

    def run(self) -> int:
        """Run the session processing loop.

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            self.initialize()

            # Get list of all available task IDs
            logger.info("Fetching available task IDs from Exgentic MCP server")
            task_ids = self.exgentic.get_task_ids()
            logger.info(f"Found {len(task_ids)} tasks to process")

            max_workers = self.config.exgentic.max_parallel_sessions
            
            # Always use ThreadPoolExecutor (works for both sequential and parallel)
            logger.info(f"Processing sessions with {max_workers} worker(s)")
            
            # Collect all session data first
            sessions = list(self.exgentic.iterate_sessions(task_ids))
            
            # Process sessions using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all sessions
                future_to_session = {
                    executor.submit(self.process_session, session_data): session_data
                    for session_data in sessions
                }
                
                # Process results as they complete
                for future in as_completed(future_to_session):
                    session_data = future_to_session[future]
                    try:
                        result = future.result()
                        self.summary.add_result(result)
                        
                        # Check abort on failure
                        if not result.success and self.config.exgentic.abort_on_failure:
                            logger.error("Aborting due to session failure (ABORT_ON_FAILURE=true)")
                            # Cancel remaining futures
                            for f in future_to_session:
                                f.cancel()
                            break
                    except Exception as e:
                        logger.error(f"Session {session_data.session_id} raised exception: {e}")
                        # Create a failure result
                        result = SessionResult(
                            session_id=session_data.session_id,
                            success=False,
                            latency_seconds=0,
                            evaluation_result=False,
                            error=str(e),
                        )
                        self.summary.add_result(result)

            # Print summary
            self.summary.print_summary(max_parallel_sessions=self.max_parallel_sessions)

            # Return success if at least one session succeeded
            if any(r.success for r in self.summary.results):
                return 0
            else:
                return 1

        except Exception as e:
            logger.exception(f"Fatal error in runner: {e}")
            return 1
        finally:
            # Shutdown components
            try:
                self.exgentic.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down Exgentic adapter: {e}")
            
            self.otel.shutdown()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Exgentic A2A Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  EXGENTIC_MCP_SERVER_URL   MCP server endpoint (required)
  EXGENTIC_MCP_TIMEOUT_SECONDS  MCP timeout in seconds (default: 60)
  MAX_TASKS                 Maximum number of sessions to process
  ABORT_ON_FAILURE          Stop on first failure (default: false)

  A2A_BASE_URL              A2A endpoint base URL (required)
  A2A_TIMEOUT_SECONDS       Request timeout in seconds (default: 300)
  A2A_AUTH_TOKEN            Bearer token for authentication
  A2A_VERIFY_TLS            Verify TLS certificates (default: true)
  A2A_ENDPOINT_PATH         Endpoint path (default: /v1/chat)

  OTEL_SERVICE_NAME         Service name for telemetry (default: exgentic-a2a-runner)
  OTEL_EXPORTER_OTLP_ENDPOINT  OTLP exporter endpoint
  OTEL_EXPORTER_OTLP_PROTOCOL  OTLP protocol (default: grpc)
  OTEL_RESOURCE_ATTRIBUTES  Additional resource attributes
  OTEL_EXPORTER_OTLP_INSECURE  Use insecure connection for OTLP (default: true)

  LOG_LEVEL                 Log level: DEBUG, INFO, WARNING, ERROR (default: INFO)
  LOG_PROMPT                Log prompt details (default: 0)
  LOG_RESPONSE              Log response details (default: 0)
        """,
    )

    parser.add_argument(
        "--log-level",
        "-l",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Set log level (DEBUG, INFO, WARNING, ERROR). Overrides LOG_LEVEL environment variable.",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point.

    Returns:
        Exit code
    """
    args = parse_args()

    # Determine log level from args or environment
    import os
    if args.log_level:
        log_level_str = args.log_level
    else:
        # Check environment variable
        log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Set log level
    log_level = getattr(logging, log_level_str, logging.INFO)
    logging.getLogger().setLevel(log_level)
    logger.info(f"Log level set to: {log_level_str}")

    try:
        # Load configuration from environment
        config = Config.from_env()
        logger.info(f"Configuration loaded: {config}")

        # Create and run
        runner = Runner(config)
        return runner.run()

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())


