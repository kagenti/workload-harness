# Exgentic A2A Runner

A standalone Python runner that integrates Exgentic benchmarks with Kagenti agents using the A2A (Agent-to-Agent) protocol. This harness implements the execution model defined in [GitHub Issue #963](https://github.com/kagenti/kagenti/issues/963).

## Features

- **Exgentic MCP Integration**: Communicates with Exgentic MCP server for benchmark tasks
- **Sequential session processing**: One session at a time for simplicity and reliability
- **A2A protocol support**: Communicates with remote agents using the A2A protocol via JSON-RPC over HTTP
- **Session lifecycle management**: Explicit create → use → evaluate → close pattern
- **OpenTelemetry instrumentation**: Comprehensive traces, metrics, and logs
- **Strict failure handling**: Any error or timeout marks the session as failed
- **Configurable via environment variables**: Easy deployment and configuration
- **Official MCP SDK**: Uses the MCP Python SDK for reliable protocol communication

## Architecture

The runner follows this execution model for each benchmark session:

1. **Create Session**: `(session_id, task) = mcp_server.create_session()`
2. **Build Prompt**: Include session_id in task instructions
3. **Invoke Agent**: `agent.invoke_agent("{task}. Use session id {session_id}")`
4. **Evaluate Session**: `success = mcp_server.evaluate_session(session_id)`
5. **Close Session**: `mcp_server.close_session(session_id)`
6. **Record Statistics**: Track completion time and success rate

## Installation

### Prerequisites

- Python 3.11 or 3.12 (Python 3.13 is **not supported** due to dependency compatibility)
- [uv](https://docs.astral.sh/uv/) package manager
- Access to an Exgentic MCP server
- Access to an A2A-compatible agent endpoint (e.g., Kagenti generalist agent)

### Install from source

#### Deploy a kagenti cluster

```bash
git clone git@github.com:kagenti/kagenti.git
cd kagenti
./run-install.sh --env dev --preload --extra-vars '{"container_engine": "podman"}'
deployments/ansible/run-install.sh --env dev --preload --extra-vars '{"container_engine": "podman"}'
```


#### Clone and build exgentic mcp server local images
```bash
git clone git@github.com:kagenti/workload-harness.git
cd agent-examples/mcp/exgentic_benchmarks
./build.sh appworld latest # can also use tau2, gsm8k
```

#### Deploy general agent and mcp per per benchmark

```bash
git clone git@github.com:kagenti/workload-harness.git
cd workload-harness/exgentic_a2a_runner
uv sync --python 3.12
source .venv/bin/activate

# Deploys mcp server using Kagenti Tool API based on local benchmark image created above
./deploy-benchmark.sh appworld 
# Deploy a generalist agent using Kagenti Agent API that connects to the benchmark mcp
./deploy-agent.sh appworld 

# 1. Updates OPENAI_API_BASE and OPENAI_API_KEY from environment env to running deployments
# 2. Increase memory limit (workaround because was not able to specify resources on deployment)
# 3. Sets the model used by the agents
./configure-agent-and-benchmark-environment.sh appworld GCP/gemini-2.5-pro

```


## Configuration

```bash
cp example.env .env
```

Configure the .env file as needed.


### Optional Variables

| Environment Variable | Default Setting | Required? | Description |
| --- | --- | --- | --- |
| `EXGENTIC_MCP_TIMEOUT_SECONDS` | `60` | No | Timeout for MCP operations in seconds. |
| `MAX_TASKS` | `(none)` | No | Maximum number of sessions to process before exiting. |
| `ABORT_ON_FAILURE` | `false` | No | Stops processing after the first failed session when enabled. |
| `A2A_TIMEOUT_SECONDS` | `300` | No | Timeout for each A2A request in seconds. |
| `A2A_AUTH_TOKEN` | `(none)` | No | Bearer token sent for A2A endpoint authentication. |
| `A2A_VERIFY_TLS` | `true` | No | Whether TLS certificates are verified for HTTPS requests. |
| `A2A_ENDPOINT_PATH` | `/v1/chat` | No | Endpoint path appended to `A2A_BASE_URL` for requests. |
| `OTEL_SERVICE_NAME` | `exgentic-a2a-runner` | No | OpenTelemetry service name reported with traces. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `(none)` | No | OTLP collector endpoint used to export telemetry. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` | No | OTLP transport protocol (`grpc` or `http/protobuf`). |
| `OTEL_RESOURCE_ATTRIBUTES` | `(none)` | No | Additional OpenTelemetry resource attributes (`key=value`). |
| `OTEL_INSTRUMENT_REQUESTS` | `true` | No | Enables automatic instrumentation for HTTP requests. |
| `OTEL_EXPORTER_OTLP_INSECURE` | `true` | No | Use insecure connection for OTLP exporter. |
| `LOG_PROMPT` | `0` | No | Enables logging of prompt payloads for debugging. |
| `LOG_RESPONSE` | `0` | No | Enables logging of response payloads for debugging. |

## Usage

### Basic Usage

```bash
./evaluate_benchmark.sh appworld
```

## Output

### Console Summary

At the end of each run, a summary is printed:

```
============================================================
RUN SUMMARY
============================================================
Sessions Attempted:   100
Sessions Succeeded:   95
Sessions Failed:      5
Evaluation Success:   92.6%
Total Wall Time:      1234.56s
Average Latency:      12345.67ms
P50 Latency:          10000.00ms
P95 Latency:          20000.00ms
============================================================
```

### OpenTelemetry Data

The runner emits comprehensive telemetry:

#### Traces

Each session creates a span (`exgentic_a2a.session`) with:

**Attributes:**
- `exgentic.session_id`: Session identifier
- `exgentic.mcp_server_url`: MCP server URL
- `exgentic.evaluation_result`: Whether evaluation was successful
- `a2a.base_url`: A2A endpoint URL
- `a2a.timeout_seconds`: Timeout value
- `prompt.chars`: Prompt size in characters
- `response.chars`: Response size in characters
- `session.status`: `success` or `failed`
- `a2a.duration_ms`: End-to-end A2A operation latency in milliseconds

**Child spans:**
- `exgentic_a2a.prompt.build`: Prompt construction
- `exgentic_a2a.a2a.send_prompt`: End-to-end A2A `send_prompt` call
- `exgentic_a2a.mcp.evaluate_session`: Session evaluation
- `exgentic_a2a.mcp.close_session`: Session cleanup

**Auto-instrumented HTTP spans:**
- Outbound `requests` spans for agent-card discovery, `message/send`, and `tasks/get` calls

**Events:**
- `prompt_built`: When prompt is constructed
- `session_failed`: When session fails (includes error details)

#### Metrics

**Counters:**
- `exgentic_a2a_sessions_total{status=success|failed}`: Total sessions processed
- `exgentic_a2a_errors_total{error_type=...}`: Total errors by type

**Histograms:**
- `exgentic_a2a_session_latency_ms`: End-to-end session latency
- `exgentic_a2a_evaluation_latency_ms`: Evaluation operation latency
- `exgentic_a2a_session_creation_latency_ms`: Session creation latency
- `exgentic_a2a_a2a_latency_ms`: A2A request latency
- `exgentic_a2a_prompt_size_chars`: Prompt size distribution
- `exgentic_a2a_response_size_chars`: Response size distribution

**Gauge:**
- `exgentic_a2a_inflight_sessions`: Current sessions in flight (0 or 1)

## Key Differences from AppWorld Runner

| Aspect | AppWorld Runner | Exgentic Runner |
|--------|----------------|-----------------|
| **Task Source** | AppWorld dataset enumeration | MCP server `create_session` |
| **Protocol** | Direct AppWorld API | MCP protocol |
| **Session Management** | Implicit (AppWorld context) | Explicit (create/evaluate/close) |
| **Evaluation** | AppWorld evaluation system | MCP `evaluate_session` |
| **Prompt Format** | Task + supervisor + apps | Task + session_id |
| **Dependencies** | `appworld` package | `mcp` package |

## Execution Flow

```
┌─────────────────────────────────────────────────────────┐
│                  For Each Session                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. Create Session                                      │
│     └─> MCP: create_session() → (session_id, task)    │
│                                                         │
│  2. Build Prompt                                        │
│     └─> Include session_id in instructions             │
│                                                         │
│  3. Invoke Agent                                        │
│     └─> A2A: send_prompt(prompt) → response           │
│                                                         │
│  4. Evaluate Session                                    │
│     └─> MCP: evaluate_session(session_id) → success   │
│                                                         │
│  5. Close Session                                       │
│     └─> MCP: close_session(session_id)                │
│                                                         │
│  6. Record Statistics                                   │
│     └─> Track time, success, evaluation result         │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Current Limitations

- Sequential execution only (no concurrency)
- No retry mechanism for failed operations
- No streaming response support
- Assumes MCP server is already configured for specific benchmark

## Troubleshooting

### MCP Connection Issues

If you see errors connecting to the MCP server:
- Verify `EXGENTIC_MCP_SERVER_URL` is correct
- Check that the MCP server is running and accessible
- Ensure the MCP server supports the required tools: `create_session`, `evaluate_session`, `close_session`

### A2A Communication Issues

If the agent doesn't respond or times out:
- Verify `A2A_BASE_URL` is correct
- Check `A2A_TIMEOUT_SECONDS` is sufficient for your tasks
- Ensure the agent is A2A-compatible and running
- Check if `A2A_AUTH_TOKEN` is required and set correctly

### Session Evaluation Failures

If sessions complete but evaluation fails:
- Check agent logs to see if it's using the session_id correctly
- Verify the agent has access to the benchmark tools via MCP
- Ensure the agent is calling tools with the correct session_id parameter

## Development

### Running Tests

```bash
uv run pytest
```

### Code Formatting

```bash
uv run black exgentic_a2a_runner/
```

### Type Checking

```bash
uv run mypy exgentic_a2a_runner/
```

## Contributing

Contributions are welcome! Please ensure:
- Code follows the existing style
- Tests pass
- Documentation is updated
- Commit messages are clear

## License

See LICENSE file in the repository root.

## Support

For issues and questions:
- GitHub Issues: https://github.com/kagenti/workload-harness/issues
- Related Issue: https://github.com/kagenti/kagenti/issues/963