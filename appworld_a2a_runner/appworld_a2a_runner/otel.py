"""OpenTelemetry instrumentation for AppWorld A2A Runner.

Provides traces, metrics, and logs for monitoring task execution.
"""
import logging
import time
from contextlib import contextmanager
from typing import Iterator, Optional

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Status, StatusCode

from .config import OTELConfig

logger = logging.getLogger(__name__)


class OTELInstrumentation:
    """OpenTelemetry instrumentation manager."""
    
    def __init__(self, config: OTELConfig):
        """Initialize OTEL instrumentation.
        
        Args:
            config: OTEL configuration
        """
        self.config = config
        self.tracer: Optional[trace.Tracer] = None
        self.meter: Optional[metrics.Meter] = None
        self._trace_provider: Optional[TracerProvider] = None
        self._meter_provider: Optional[MeterProvider] = None
        
        # Metrics
        self.tasks_counter: Optional[metrics.Counter] = None
        self.errors_counter: Optional[metrics.Counter] = None
        self.task_latency_histogram: Optional[metrics.Histogram] = None
        self.a2a_latency_histogram: Optional[metrics.Histogram] = None
        self.prompt_size_histogram: Optional[metrics.Histogram] = None
        self.response_size_histogram: Optional[metrics.Histogram] = None
        self.inflight_gauge: Optional[metrics.UpDownCounter] = None
        self._requests_instrumented = False
    
    def initialize(self) -> None:
        """Initialize OTEL providers and instruments."""
        logger.info("Initializing OpenTelemetry instrumentation")
        
        # Create resource with service name and attributes
        resource_attrs = {"service.name": self.config.service_name}
        if self.config.resource_attributes:
            # Parse resource attributes (format: key1=val1,key2=val2)
            for attr in self.config.resource_attributes.split(","):
                if "=" in attr:
                    key, value = attr.split("=", 1)
                    resource_attrs[key.strip()] = value.strip()
        
        resource = Resource.create(resource_attrs)
        
        # Initialize tracing
        self._initialize_tracing(resource)
        
        # Initialize auto-instrumentation
        self._initialize_auto_instrumentation()
        
        # Initialize metrics
        self._initialize_metrics(resource)
        
        logger.info("OpenTelemetry instrumentation initialized")
    
    def _initialize_tracing(self, resource: Resource) -> None:
        """Initialize tracing provider and exporter."""
        trace_provider = TracerProvider(resource=resource)
        
        if self.config.exporter_endpoint:
            # Use OTLP exporter
            logger.info(f"Configuring OTLP trace exporter: {self.config.exporter_endpoint}")
            span_exporter = OTLPSpanExporter(
                endpoint=self.config.exporter_endpoint,
                insecure=self.config.exporter_insecure,
            )
        else:
            # Use console exporter for development
            logger.info("Using console trace exporter (no OTLP endpoint configured)")
            span_exporter = ConsoleSpanExporter()
        
        trace_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(trace_provider)
        self._trace_provider = trace_provider

        self.tracer = trace.get_tracer(__name__)
    
    def _initialize_auto_instrumentation(self) -> None:
        """Initialize opt-in auto instrumentation."""
        if not self.config.instrument_requests:
            logger.info("Requests auto-instrumentation disabled")
            return
        
        if self._requests_instrumented:
            return
        
        RequestsInstrumentor().instrument()
        self._requests_instrumented = True
        logger.info("Enabled OpenTelemetry requests auto-instrumentation")
    
    def _initialize_metrics(self, resource: Resource) -> None:
        """Initialize metrics provider and instruments."""
        metric_readers = []
        
        if self.config.exporter_endpoint:
            # Use OTLP exporter
            logger.info(f"Configuring OTLP metric exporter: {self.config.exporter_endpoint}")
            metric_exporter = OTLPMetricExporter(
                endpoint=self.config.exporter_endpoint,
                insecure=self.config.exporter_insecure,
            )
            metric_reader = PeriodicExportingMetricReader(metric_exporter)
            metric_readers.append(metric_reader)
        else:
            # No exporter configured - metrics will be collected but not exported
            logger.info("No OTLP endpoint configured, metrics will not be exported")
        
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=metric_readers,
        )
        metrics.set_meter_provider(meter_provider)
        self._meter_provider = meter_provider

        self.meter = metrics.get_meter(__name__)
        
        # Create metric instruments
        self.tasks_counter = self.meter.create_counter(
            name="a2a_proxy_tasks_total",
            description="Total number of tasks processed",
            unit="1",
        )
        
        self.errors_counter = self.meter.create_counter(
            name="a2a_proxy_errors_total",
            description="Total number of errors",
            unit="1",
        )
        
        self.task_latency_histogram = self.meter.create_histogram(
            name="a2a_proxy_task_latency_ms",
            description="Task processing latency in milliseconds",
            unit="ms",
        )
        
        self.a2a_latency_histogram = self.meter.create_histogram(
            name="a2a_proxy_a2a_latency_ms",
            description="A2A request latency in milliseconds",
            unit="ms",
        )
        
        self.prompt_size_histogram = self.meter.create_histogram(
            name="a2a_proxy_prompt_size_chars",
            description="Prompt size in characters",
            unit="chars",
        )
        
        self.response_size_histogram = self.meter.create_histogram(
            name="a2a_proxy_response_size_chars",
            description="Response size in characters",
            unit="chars",
        )
        
        self.inflight_gauge = self.meter.create_up_down_counter(
            name="a2a_proxy_inflight_tasks",
            description="Number of tasks currently in flight",
            unit="1",
        )
    
    def shutdown(self) -> None:
        """Shut down OTEL providers to flush pending spans and metrics."""
        logger.info("Shutting down OpenTelemetry providers")
        if self._trace_provider:
            self._trace_provider.shutdown()
        if self._meter_provider:
            self._meter_provider.shutdown()

    @contextmanager
    def task_span(
        self,
        task_id: str,
        dataset: str,
        a2a_base_url: str,
        a2a_timeout: int,
    ) -> Iterator[trace.Span]:
        """Create a span for task processing.
        
        Args:
            task_id: Task identifier
            dataset: Dataset name
            a2a_base_url: A2A endpoint URL (sanitized)
            a2a_timeout: A2A timeout in seconds
            
        Yields:
            Span object for adding events and attributes
        """
        if not self.tracer:
            raise RuntimeError("OTEL not initialized")
        
        # Increment inflight gauge
        if self.inflight_gauge:
            self.inflight_gauge.add(1)
        
        start_time = time.time()
        
        with self.tracer.start_as_current_span("a2a_proxy.task") as span:
            # Set span attributes
            span.set_attribute("appworld.task_id", task_id)
            span.set_attribute("appworld.dataset", dataset)
            span.set_attribute("a2a.base_url", a2a_base_url)
            span.set_attribute("a2a.timeout_seconds", a2a_timeout)
            
            try:
                yield span
            finally:
                # Decrement inflight gauge
                if self.inflight_gauge:
                    self.inflight_gauge.add(-1)
                
                # Record task latency
                latency_ms = (time.time() - start_time) * 1000
                if self.task_latency_histogram:
                    self.task_latency_histogram.record(latency_ms)
    
    @contextmanager
    def child_span(self, name: str) -> Iterator[trace.Span]:
        """Create a child span under the current context."""
        if not self.tracer:
            raise RuntimeError("OTEL not initialized")
        
        with self.tracer.start_as_current_span(name) as span:
            yield span
    
    def record_prompt(self, span: trace.Span, prompt: str) -> None:
        """Record prompt information.
        
        Args:
            span: Current span
            prompt: Prompt text
        """
        prompt_chars = len(prompt)
        span.set_attribute("prompt.chars", prompt_chars)
        span.add_event("prompt_built")
        
        if self.prompt_size_histogram:
            self.prompt_size_histogram.record(prompt_chars)
    
    def record_a2a_request(
        self,
        span: trace.Span,
        duration_ms: float,
    ) -> None:
        """Record A2A request metrics.
        
        Args:
            span: Current span
            duration_ms: Request duration in milliseconds
        """
        span.set_attribute("a2a.duration_ms", duration_ms)
        
        if self.a2a_latency_histogram:
            self.a2a_latency_histogram.record(duration_ms)
    
    def record_response(self, span: trace.Span, response: str) -> None:
        """Record response information.
        
        Args:
            span: Current span
            response: Response text
        """
        response_chars = len(response)
        span.set_attribute("response.chars", response_chars)
        
        if self.response_size_histogram:
            self.response_size_histogram.record(response_chars)
    
    def record_success(self, span: trace.Span) -> None:
        """Record successful task completion.
        
        Args:
            span: Current span
        """
        span.set_attribute("task.status", "success")
        span.set_status(Status(StatusCode.OK))
        
        if self.tasks_counter:
            self.tasks_counter.add(1, {"status": "success"})
    
    def record_failure(
        self,
        span: trace.Span,
        error: Exception,
        error_type: str,
    ) -> None:
        """Record task failure.
        
        Args:
            span: Current span
            error: Exception that caused failure
            error_type: Error type classification
        """
        span.set_attribute("task.status", "failed")
        span.add_event(
            "task_failed",
            attributes={
                "error.type": error_type,
                "error.message": str(error),
            },
        )
        span.set_status(Status(StatusCode.ERROR, str(error)))
        span.record_exception(error)
        
        if self.tasks_counter:
            self.tasks_counter.add(1, {"status": "failed"})
        
        if self.errors_counter:
            self.errors_counter.add(1, {"error_type": error_type})

# Made with Bob
