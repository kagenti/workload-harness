# Exgentic A2A Runner

A standalone Python runner that integrates Exgentic benchmarks with Kagenti agents using the A2A (Agent-to-Agent) protocol. This harness implements the execution model defined in [GitHub Issue #963](https://github.com/kagenti/kagenti/issues/963).

## Features

- **Exgentic MCP Integration**: Communicates with Exgentic MCP server for benchmark tasks
- **Parallel session processing**: Configurable concurrency for efficient benchmark execution
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

> **⏱️ Estimated Setup Time:** ~15 minutes (excluding container image pulls)

### Prerequisites

- Python 3.11 or 3.12 (Python 3.13+ is **not supported** due to dependency compatibility)
  - **Note:** The `uv` package manager will automatically use Python 3.12 when you run `uv sync --python 3.12`, regardless of your system Python version
- [uv](https://docs.astral.sh/uv/) package manager
- kubectl configured with `kind-kagenti` context
- Kagenti cluster running with:
  - Kagenti backend in `kagenti-system` namespace
  - Keycloak in `keycloak` namespace
  - `team1` namespace for deployments

### Install from source

#### Deploy a kagenti cluster

```bash
git clone git@github.com:kagenti/kagenti.git
cd kagenti

# Create secret values file (required before installation)
cp deployments/envs/secret_values.yaml.example deployments/envs/.secret_values.yaml
# Edit .secret_values.yaml if you need to add API keys or credentials

deployments/ansible/run-install.sh --env dev --preload --extra-vars '{"container_engine": "podman"}'
```


#### Clone and build exgentic mcp server and agent local images
```bash
git clone git@github.com:yoavkatz/agent-examples.git
cd agent-examples
git checkout feature/exgentic-mcp-server
cd mcp/exgentic_benchmarks
./build.sh tau2  # can also use appworld, gsm8k
cd ../../a2a/exgentic_agent
./build.sh tool_calling
```

#### Deploy agent and MCP server per benchmark

```bash
git clone git@github.com:yoavkatz/workload-harness.git
cd workload-harness
git checkout feature/exgentic-a2a-runner
cd exgentic_a2a_runner
uv sync --python 3.12
source .venv/bin/activate

# Deploy and configure MCP server using Kagenti Tool API
# This script now combines deployment and configuration in one step
./deploy-benchmark.sh tau2

# Deploy and configure agent using Kagenti Agent API
# This script now combines deployment and configuration in one step
./deploy-agent.sh tau2 tool_calling
```

**Note:** Both deployment scripts now accept named parameters for optional settings:

**Benchmark Deployment:**
```bash
# Basic deployment with defaults (model: Azure/gpt-4o, keycloak: admin/admin)
./deploy-benchmark.sh tau2

# Deploy with custom model
./deploy-benchmark.sh tau2 --model Azure/gpt-4o-mini

# Deploy with custom Keycloak credentials
./deploy-benchmark.sh tau2 --model Azure/gpt-4o-mini --keycloak-user admin --keycloak-pass admin

# Show help
./deploy-benchmark.sh --help
```

**Agent Deployment:**
```bash
# Basic deployment with defaults (model: Azure/gpt-4o, keycloak: admin/admin)
./deploy-agent.sh tau2 tool_calling

# Deploy with custom model
./deploy-agent.sh tau2 tool_calling --model Azure/gpt-4o-mini

# Deploy with custom Keycloak credentials
./deploy-agent.sh tau2 tool_calling --model Azure/gpt-4o-mini --keycloak-user admin --keycloak-pass admin

# Show help
./deploy-agent.sh --help
```

**Agent Naming:** Underscores in agent names are automatically converted to hyphens for Kubernetes compatibility (e.g., `tool_calling` becomes `tool-calling`).

**Important:** Both deployment scripts now combine deployment and configuration steps:

**`deploy-benchmark.sh`** will:
1. Deploy the MCP server to the Kagenti cluster
2. Automatically configure environment variables (OPENAI_API_BASE, OPENAI_API_KEY)
3. Set memory limits and model settings
4. Wait for the deployment to be ready

**`deploy-agent.sh`** will:
1. Deploy the agent to the Kagenti cluster
2. Automatically configure environment variables (OPENAI_API_BASE, OPENAI_API_KEY, LLM_MODEL)
3. Set model settings (LLM_MODEL, EXGENTIC_SET_AGENT_MODEL)
4. Wait for the deployment to be ready

For appworld benchmark, use gemini-2.5-pro or other models, because OpenAI models cannot handle the number of tools in appworld without special tool shortlisting.


## Configuration

### Before Running Evaluations

**Required:** Create and configure your environment file:

```bash
cp example.env .env
```

Then edit the .env file as needed.

### Main Configuration

| Environment Variable | Default | Description |
| --- | --- | --- |
| `MAX_TASKS` | `(none)` | Maximum number of sessions to process. Useful for testing with a subset. |
| `MAX_PARALLEL_SESSIONS` | `1` | Number of sessions to run concurrently. Set higher for parallel execution. |
| `ABORT_ON_FAILURE` | `false` | Stop processing after the first failed session. |

### Debug Configuration

| Environment Variable | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Log level for the runner. Set to `DEBUG` for verbose logging with detailed debug information. Options: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `LOG_PROMPT` | `0` | Log prompt payloads for debugging (1 to enable). |
| `LOG_RESPONSE` | `0` | Log response payloads for debugging (1 to enable). |

### Tracing Configuration (OpenTelemetry)

| Environment Variable | Default | Description |
| --- | --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `(none)` | OTLP collector endpoint (e.g., `http://localhost:4317` for Jaeger). If not set, no traces are exported. |
| `OTEL_SERVICE_NAME` | `exgentic-a2a-runner` | Service name in traces. |
| `OTEL_RESOURCE_ATTRIBUTES` | `(none)` | Additional resource attributes (format: `key1=val1,key2=val2`). |
| `OTEL_INSTRUMENT_REQUESTS` | `true` | Auto-instrument HTTP requests. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` | OTLP protocol (`grpc` or `http/protobuf`). |
| `OTEL_EXPORTER_OTLP_INSECURE` | `true` | Use insecure OTLP connection. |

### Advanced Configuration

| Environment Variable | Default | Description |
| --- | --- | --- |
| `EXGENTIC_MCP_TIMEOUT_SECONDS` | `60` | Timeout for MCP operations. |
| `A2A_TIMEOUT_SECONDS` | `300` | Timeout for A2A requests. |
| `A2A_AUTH_TOKEN` | `(none)` | Bearer token for A2A authentication. |
| `A2A_VERIFY_TLS` | `true` | Verify TLS certificates for HTTPS. |
| `A2A_ENDPOINT_PATH` | `/v1/chat` | Endpoint path for A2A requests. |

## Usage

### Running Benchmarks

The `evaluate_benchmark.sh` script automatically:
- Sets up port forwarding (MCP server on localhost:7770, A2A agent on localhost:7701)
- Waits for pods to be ready
- Tests connectivity to both services
- Runs the benchmark evaluation
- Cleans up port forwards on exit

```bash
./evaluate_benchmark.sh tau2 tool_calling
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

## OpenTelemetry and Observability

### Setting up Local Jaeger for Tracing

To visualize traces and metrics locally, you can run Jaeger using Docker:

#### 1. Start Jaeger All-in-One

```bash
docker run -d --name jaeger \
  -e COLLECTOR_OTLP_ENABLED=true \
  -p 16686:16686 \
  -p 4317:4317 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest
```

This starts Jaeger with:
- **UI**: http://localhost:16686 (view traces)
- **OTLP gRPC**: localhost:4317 (for trace/metric export)
- **OTLP HTTP**: localhost:4318 (alternative protocol)

#### 2. Configure the Runner

Update your `.env` file to enable OTEL export:

```bash
# Enable OTLP export to Jaeger
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

#### 3. Run Your Benchmark

```bash
./evaluate_benchmark.sh appworld
```

#### 4. View Traces in Jaeger UI

1. Open http://localhost:16686 in your browser
2. Select `exgentic-a2a-runner` from the Service dropdown
3. Click "Find Traces" to see all sessions
4. Click on individual traces to see detailed spans

#### 5. Stop Jaeger

```bash
docker stop jaeger
docker rm jaeger
```

### What Gets Traced

When OTEL is enabled, you'll see:

- **Session spans**: Complete session lifecycle with timing
- **MCP operations**: create_session, evaluate_session, close_session
- **A2A requests**: Agent invocations with request/response sizes
- **HTTP calls**: Auto-instrumented outbound requests
- **Errors**: Failed operations with exception details

## Current Limitations

- No retry mechanism for failed operations
- No streaming response support
- Tested only with local kind Kagenti installation with Podman (not tested with Docker)

## Troubleshooting


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

## Additional Resources

- **Kagenti UI**: Access at http://kagenti-ui.localtest.me:8080/ to monitor deployments
- **GitHub Issues**: https://github.com/kagenti/workload-harness/issues
- **Related Issue**: https://github.com/kagenti/kagenti/issues/963

## Next Steps

After successful test run:
1. Increase `MAX_TASKS` in `.env` for longer runs
2. Adjust `MAX_PARALLEL_SESSIONS` for different concurrency levels
3. Enable OTLP exporter for telemetry collection
4. Deploy different benchmarks (gsm8k, tau2, appworld)
5. Test with various models via configure script
6. Analyze results and agent performance in Kagenti UI