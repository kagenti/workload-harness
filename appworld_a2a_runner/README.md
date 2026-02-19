# AppWorld A2A Proxy Runner

A standalone Python runner that uses AppWorld to enumerate tasks and fetch task text, then calls a remote agent over A2A (Agent-to-Agent) protocol with a plain-text prompt, collects the plain-text response, and emits OpenTelemetry (OTEL) telemetry.

## Features

- **Standalone execution**: Not integrated with AppWorld's experiment framework
- **Sequential task processing**: One task at a time for simplicity
- **A2A protocol support**: Communicates with remote agents using the A2A protocol via JSON-RPC over HTTP
- **OpenTelemetry instrumentation**: Comprehensive traces, metrics, and logs
- **Strict failure handling**: Any error or timeout marks the task as failed
- **Configurable via environment variables**: Easy deployment and configuration
- **No SDK dependencies**: Uses plain HTTP requests instead of the A2A SDK to avoid dependency conflicts with AppWorld

## Installation

### Prerequisites

- Python 3.11 or higher
- Access to an A2A-compatible agent endpoint such as [Simple Generalist in Kagenti examples](a2a/simple_generalist/src/simple_generalist)
- Access to the AppWorld API server such as [AppWorld Tool in Kagenti](https://github.com/kagenti/agent-examples/tree/main/mcp/appworld_apis)
- Deploy both the agent and the AppWorld API server on Kagenti. Expose them as external services or `port-forward` to their exposed ports. For the AppWorld API server, you will need to access its REST API interface, which is by default exposed on port `8000`


### Install from source

```bash
git clone git@github.com:kagenti/workload-harness.git
cd appworld_a2a_runner
uv venv
source .venv/bin/activate
uv sync
```

## Configuration

```
cp example.env .env
```
Configure the .env file as needed

Required Variables
| Environment Variable | Default Setting | Required? | Description |
| --- | --- | --- | --- |
| `A2A_BASE_URL` | `(none)` | Yes | Base URL for the target agent to run the tests against. Must be A2A compatible.|
| `APPWORLD_DATASET` | `test_normal` | Yes | AppWorld dataset to run (for example `test_normal` or `test_challenge`). |
| `APPWORLD_REMOTE_APIS_URL` | `(none)` | Yes | URL for the AppWorld remote APIs server. |

Optional Variables
| Environment Variable | Default Setting | Required? | Description |
| --- | --- | --- | --- |
| `A2A_TIMEOUT_SECONDS` | `300` | No | Timeout for each A2A request in seconds. |
| `A2A_AUTH_TOKEN` | `(none)` | No | Bearer token sent for A2A endpoint authentication. |
| `A2A_VERIFY_TLS` | `true` | No | Whether TLS certificates are verified for HTTPS requests. |
| `A2A_ENDPOINT_PATH` | `/v1/chat` | No | Endpoint path appended to `A2A_BASE_URL` for requests. |
| `APPWORLD_ROOT` | `(none)` | No | Overrides the AppWorld root directory path. |
| `MAX_TASKS` | `(none)` | No | Maximum number of tasks to process before exiting. |
| `ABORT_ON_FAILURE` | `false` | No | Stops processing after the first failed task when enabled. |
| `OTEL_SERVICE_NAME` | `appworld-a2a-proxy` | No | OpenTelemetry service name reported with traces. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `(none)` | No | OTLP collector endpoint used to export telemetry. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` | No | OTLP transport protocol (`grpc` or `http/protobuf`). |
| `OTEL_RESOURCE_ATTRIBUTES` | `(none)` | No | Additional OpenTelemetry resource attributes (`key=value`). |
| `OTEL_INSTRUMENT_REQUESTS` | `true` | No | Enables automatic instrumentation for HTTP requests. |
| `LOG_PROMPT` | `0` | No | Enables logging of prompt payloads for debugging. |
| `LOG_RESPONSE` | `0` | No | Enables logging of response payloads for debugging. |


## Usage

### Basic Usage

```bash
uv run appworld-a2a-runner
```

## Output

### Console Summary

At the end of each run, a summary is printed:

```
============================================================
RUN SUMMARY
============================================================
Dataset:           test_normal
Tasks Attempted:   100
Tasks Succeeded:   95
Tasks Failed:      5
Total Wall Time:   1234.56s
Average Latency:   12345.67ms
P50 Latency:       10000.00ms
P95 Latency:       20000.00ms
============================================================
```

### OpenTelemetry Data

The runner emits comprehensive telemetry:

#### Traces

Each task creates a span (`a2a_proxy.task`) with:

**Attributes:**
- `appworld.task_id`: Task identifier
- `appworld.dataset`: Dataset name
- `a2a.base_url`: A2A endpoint URL
- `a2a.timeout_seconds`: Timeout value
- `prompt.chars`: Prompt size in characters
- `response.chars`: Response size in characters
- `task.status`: `success` or `failed`
- `a2a.duration_ms`: End-to-end A2A operation latency in milliseconds

**Child spans:**
- `a2a_proxy.prompt.build`: Prompt construction
- `a2a_proxy.a2a.send_prompt`: End-to-end A2A `send_prompt` call

**Auto-instrumented HTTP spans:**
- Outbound `requests` spans for agent-card discovery, `message/send`, and `tasks/get` calls

**Events:**
- `prompt_built`: When prompt is constructed
- `task_failed`: When task fails (includes error details)

#### Metrics

**Counters:**
- `a2a_proxy_tasks_total{status=success|failed}`: Total tasks processed
- `a2a_proxy_errors_total{error_type=...}`: Total errors by type

**Histograms:**
- `a2a_proxy_task_latency_ms`: End-to-end task latency
- `a2a_proxy_a2a_latency_ms`: A2A request latency
- `a2a_proxy_prompt_size_chars`: Prompt size distribution
- `a2a_proxy_response_size_chars`: Response size distribution

**Gauge:**
- `a2a_proxy_inflight_tasks`: Current tasks in flight (0 or 1)



## Current Limitations

- Sequential execution only (no concurrency)
- No retry mechanism
- No streaming response support
- No structured response parsing
