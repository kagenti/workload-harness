"""Main runner for AppWorld A2A Proxy.

Orchestrates task enumeration, A2A calls, and telemetry collection.
"""
import argparse
import logging
import sys
import time
from typing import List, Optional

from .a2a_client import A2AProxyClient
from .appworld_adapter import AppWorldAdapter, TaskData
from .config import Config
from .otel import OTELInstrumentation
from .prompt import build_prompt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class TaskResult:
    """Result of a single task execution."""
    
    def __init__(
        self,
        task_id: str,
        success: bool,
        latency_ms: float,
        error: Optional[str] = None,
        response_chars: Optional[int] = None,
    ):
        self.task_id = task_id
        self.success = success
        self.latency_ms = latency_ms
        self.error = error
        self.response_chars = response_chars


class RunSummary:
    """Summary of the entire run."""
    
    def __init__(self, dataset: str):
        self.dataset = dataset
        self.start_time = time.time()
        self.results: List[TaskResult] = []
    
    def add_result(self, result: TaskResult) -> None:
        """Add a task result."""
        self.results.append(result)
    
    def get_summary(self) -> dict:
        """Get summary statistics."""
        total_time = time.time() - self.start_time
        attempted = len(self.results)
        succeeded = sum(1 for r in self.results if r.success)
        failed = attempted - succeeded
        
        latencies = [r.latency_ms for r in self.results]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        
        # Calculate percentiles
        sorted_latencies = sorted(latencies)
        p50 = sorted_latencies[len(sorted_latencies) // 2] if sorted_latencies else 0
        p95_idx = min(int(len(sorted_latencies) * 0.95), len(sorted_latencies) - 1)
        p95 = sorted_latencies[p95_idx] if sorted_latencies else 0
        
        return {
            "dataset": self.dataset,
            "tasks_attempted": attempted,
            "tasks_succeeded": succeeded,
            "tasks_failed": failed,
            "total_wall_time_seconds": total_time,
            "average_latency_ms": avg_latency,
            "p50_latency_ms": p50,
            "p95_latency_ms": p95,
        }
    
    def print_summary(self) -> None:
        """Print summary to console."""
        summary = self.get_summary()
        
        print("\n" + "=" * 60)
        print("RUN SUMMARY")
        print("=" * 60)
        print(f"Dataset:           {summary['dataset']}")
        print(f"Tasks Attempted:   {summary['tasks_attempted']}")
        print(f"Tasks Succeeded:   {summary['tasks_succeeded']}")
        print(f"Tasks Failed:      {summary['tasks_failed']}")
        print(f"Total Wall Time:   {summary['total_wall_time_seconds']:.2f}s")
        print(f"Average Latency:   {summary['average_latency_ms']:.2f}ms")
        print(f"P50 Latency:       {summary['p50_latency_ms']:.2f}ms")
        print(f"P95 Latency:       {summary['p95_latency_ms']:.2f}ms")
        print("=" * 60 + "\n")


class Runner:
    """Main runner orchestrating task execution."""
    
    def __init__(self, config: Config):
        """Initialize runner.
        
        Args:
            config: Complete configuration
        """
        self.config = config
        self.appworld = AppWorldAdapter(config.appworld)
        self.a2a_client = A2AProxyClient(config.a2a)
        self.otel = OTELInstrumentation(config.otel)
        self.summary = RunSummary(config.appworld.dataset)
    
    def initialize(self) -> None:
        """Initialize all components."""
        logger.info("Initializing runner components")
        self.otel.initialize()
        self.appworld.initialize()
        logger.info("Runner initialization complete")
    
    def process_task(self, task_data: TaskData) -> TaskResult:
        """Process a single task.
        
        Args:
            task_data: Task data from AppWorld
            
        Returns:
            TaskResult with execution details
        """
        task_id = task_data.task_id
        start_time = time.time()
        
        logger.info(f"Processing task: {task_id}")
        
        # Start OTEL span
        with self.otel.task_span(
            task_id=task_id,
            dataset=self.config.appworld.dataset,
            a2a_base_url=self.config.a2a.base_url,
            a2a_timeout=self.config.a2a.timeout_seconds,
        ) as span:
            try:
                # Build prompt
                with self.otel.child_span("a2a_proxy.prompt.build"):
                    prompt = build_prompt(task_data.instruction, task_data.supervisor, task_data.app_descriptions)
                self.otel.record_prompt(span, prompt)
                
                if self.config.debug.log_prompt:
                    logger.debug(f"Prompt length: {len(prompt)} chars")
                
                # Send A2A request
                a2a_start = time.time()
                with self.otel.child_span("a2a_proxy.a2a.send_prompt"):
                    response = self.a2a_client.send_prompt(prompt)
                a2a_duration_ms = (time.time() - a2a_start) * 1000
                
                self.otel.record_a2a_request(span, a2a_duration_ms)
                self.otel.record_response(span, response)
                
                if self.config.debug.log_response:
                    logger.debug(f"Response length: {len(response)} chars")
                
                # Record success
                self.otel.record_success(span)
                
                latency_ms = (time.time() - start_time) * 1000
                logger.info(f"Task {task_id} succeeded in {latency_ms:.2f}ms")
                
                return TaskResult(
                    task_id=task_id,
                    success=True,
                    latency_ms=latency_ms,
                    response_chars=len(response),
                )
                
            except Exception as e:
                # Classify error type
                error_type = type(e).__name__
                error_msg = str(e)
                
                logger.error(f"Task {task_id} failed: {error_type}: {error_msg}")
                
                # Record failure
                self.otel.record_failure(span, e, error_type)
                
                latency_ms = (time.time() - start_time) * 1000
                
                return TaskResult(
                    task_id=task_id,
                    success=False,
                    latency_ms=latency_ms,
                    error=f"{error_type}: {error_msg}",
                )
    
    def run(self) -> int:
        """Run the task processing loop.
        
        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            self.initialize()

            # Process tasks sequentially
            for task_data in self.appworld.iterate_tasks():
                result = self.process_task(task_data)
                self.summary.add_result(result)

                # Check abort on failure
                if not result.success and self.config.appworld.abort_on_failure:
                    logger.error("Aborting due to task failure (ABORT_ON_FAILURE=true)")
                    break

            # Print summary
            self.summary.print_summary()

            # Return success if at least one task succeeded
            if any(r.success for r in self.summary.results):
                return 0
            else:
                return 1

        except Exception as e:
            logger.exception(f"Fatal error in runner: {e}")
            return 1
        finally:
            self.otel.shutdown()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="AppWorld A2A Proxy Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  A2A_BASE_URL              A2A endpoint base URL (required)
  A2A_TIMEOUT_SECONDS       Request timeout in seconds (default: 300)
  A2A_AUTH_TOKEN            Bearer token for authentication
  A2A_VERIFY_TLS            Verify TLS certificates (default: true)
  A2A_ENDPOINT_PATH         Endpoint path (default: /v1/chat)
  
  APPWORLD_ROOT             AppWorld root directory
  APPWORLD_DATASET          Dataset split name (required)
  APPWORLD_REMOTE_APIS_URL  AppWorld remote APIs base URL (required)
  MAX_TASKS                 Maximum number of tasks to process
  ABORT_ON_FAILURE          Stop on first failure (default: false)
  
  OTEL_SERVICE_NAME         Service name for telemetry (default: appworld-a2a-proxy)
  OTEL_EXPORTER_OTLP_ENDPOINT  OTLP exporter endpoint
  OTEL_EXPORTER_OTLP_PROTOCOL  OTLP protocol (default: grpc)
  OTEL_RESOURCE_ATTRIBUTES  Additional resource attributes
  OTEL_EXPORTER_OTLP_INSECURE  Use insecure connection for OTLP (default: true)
  
  LOG_PROMPT                Log prompt details (default: 0)
  LOG_RESPONSE              Log response details (default: 0)
        """,
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    
    return parser.parse_args()


def main() -> int:
    """Main entry point.
    
    Returns:
        Exit code
    """
    args = parse_args()
    
    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Load configuration from environment
        config = Config.from_env()
        
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

# Made with Bob
