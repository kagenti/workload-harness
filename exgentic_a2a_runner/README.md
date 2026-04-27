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
./deploy-benchmark.sh --benchmark tau2

# Deploy and configure agent using Kagenti Agent API
# This script now combines deployment and configuration in one step
./deploy-agent.sh --benchmark tau2 --agent tool_calling
```

**Note:** All deployment scripts now use named parameters:

**Benchmark Deployment:**
```bash
# Basic deployment with defaults (model: Azure/gpt-4.1, keycloak: admin/admin)
./deploy-benchmark.sh --benchmark tau2

# Deploy with custom model
./deploy-benchmark.sh --benchmark tau2 --model Azure/gpt-4o-mini

# Deploy with custom Keycloak credentials
./deploy-benchmark.sh --benchmark tau2 --model Azure/gpt-4o-mini --keycloak-user admin --keycloak-pass admin

# Show help
./deploy-benchmark.sh --help
```

**Agent Deployment:**
```bash
# Basic deployment with defaults (model: Azure/gpt-4.1, keycloak: admin/admin)
./deploy-agent.sh --benchmark tau2 --agent tool_calling

# Deploy with custom model
./deploy-agent.sh --benchmark tau2 --agent tool_calling --model Azure/gpt-4o-mini

# Deploy with custom Keycloak credentials
./deploy-agent.sh --benchmark tau2 --agent tool_calling --model Azure/gpt-4o-mini --keycloak-user admin --keycloak-pass admin

# Show help
./deploy-agent.sh --help
```

**Agent Naming:** Underscores in agent names are automatically converted to hyphens for Kubernetes compatibility (e.g., `tool_calling` becomes `tool-calling`).

**Important:** Both deployment scripts now combine deployment and configuration steps:

**`deploy-benchmark.sh`** will:
1. Deploy the MCP server to the Kagenti cluster
2. Automatically configure secrets before deployment:
   - Updates `openai-secret` with OPENAI_API_KEY (if set in environment)
   - Creates/updates `hf-secret` with HF_TOKEN (uses dummy token if not set)
3. Configure environment variables (OPENAI_API_BASE, EXGENTIC_SET_BENCHMARK_RUNNER for gsm8k)
4. Set memory limits and model settings
5. Wait for the deployment to be ready

**`deploy-agent.sh`** will:
1. Deploy the agent to the Kagenti cluster
2. Automatically configure environment variables (OPENAI_API_BASE, OPENAI_API_KEY, LLM_MODEL)
3. Set model settings (LLM_MODEL, EXGENTIC_SET_AGENT_MODEL)
4. Wait for the deployment to be ready

**Environment Variables for Deployment:**
- `OPENAI_API_KEY`: OpenAI API key (optional, updates openai-secret if set)
- `HF_TOKEN`: HuggingFace token (optional, creates hf-secret with dummy token if not set)
- `OPENAI_API_BASE`: OpenAI API base URL (optional, added to deployment env vars)

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
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `(none)` | OTLP collector endpoint (for this runner, use gRPC such as `http://localhost:4317`). If not set, no traces are exported. |
| `OTEL_SERVICE_NAME` | `exgentic-a2a-runner` | Service name in traces. |
| `OTEL_RESOURCE_ATTRIBUTES` | `(none)` | Additional resource attributes (format: `key1=val1,key2=val2`). |
| `OTEL_INSTRUMENT_REQUESTS` | `true` | Auto-instrument HTTP requests. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` | OTLP protocol. The current exporter implementation in [`OTELInstrumentation._initialize_tracing()`](exgentic_a2a_runner/exgentic_a2a_runner/otel.py:80) and [`OTELInstrumentation._initialize_metrics()`](exgentic_a2a_runner/exgentic_a2a_runner/otel.py:114) uses OTLP gRPC. |
| `OTEL_EXPORTER_OTLP_INSECURE` | `true` | Use insecure OTLP connection. |

### Advanced Configuration

| Environment Variable | Default | Description |
| --- | --- | --- |
| `EXGENTIC_MCP_TIMEOUT_SECONDS` | `60` | Timeout for MCP operations. |
| `A2A_TIMEOUT_SECONDS` | `300` | Timeout for A2A requests. |
| `A2A_AUTH_TOKEN` | `(none)` | Bearer token for A2A authentication. |
| `A2A_VERIFY_TLS` | `true` | Verify TLS certificates for HTTPS. |
| `A2A_ENDPOINT_PATH` | `/` | Endpoint path for A2A requests. |

## Usage

### All-in-One: Deploy and Evaluate

The `deploy-and-evaluate.sh` script provides a convenient way to deploy both the benchmark and agent, then run the evaluation in a single command:

```bash
./deploy-and-evaluate.sh --benchmark tau2 --agent tool_calling
./deploy-and-evaluate.sh --benchmark gsm8k --agent tool_calling --phoenix-otel
```

This script will:
1. Deploy the benchmark MCP server
2. Deploy the agent
3. Run the evaluation

When [`--phoenix-otel`](exgentic_a2a_runner/deploy-and-evaluate.sh) is supplied, it is passed through to [`evaluate-benchmark.sh`](exgentic_a2a_runner/evaluate-benchmark.sh) for Phoenix OTLP port-forwarding during the evaluation step.

**Options:**
```bash
# Basic usage with defaults
./deploy-and-evaluate.sh --benchmark tau2 --agent tool_calling

# With Phoenix OTEL forwarding during evaluation
./deploy-and-evaluate.sh --benchmark gsm8k --agent tool_calling --phoenix-otel

# With custom model
./deploy-and-evaluate.sh --benchmark tau2 --agent tool_calling --model Azure/gpt-4o-mini

# With custom Keycloak credentials
./deploy-and-evaluate.sh --benchmark tau2 --agent tool_calling --model Azure/gpt-4o-mini --keycloak-user admin --keycloak-pass admin

# Show help
./deploy-and-evaluate.sh --help
```

### Running Benchmarks

The `evaluate-benchmark.sh` script automatically:
- Sets up port forwarding (MCP server on localhost:7770, A2A agent on localhost:7701)
- Optionally port-forwards Phoenix OTLP on localhost:4317 with `--phoenix-otel`
- Waits for pods to be ready
- Tests connectivity to the forwarded services
- Runs the benchmark evaluation
- Propagates the current OpenTelemetry trace context into outbound A2A HTTP requests so the agent can continue the same distributed trace when it supports W3C trace headers
- Cleans up port forwards on exit

```bash
./evaluate-benchmark.sh --benchmark tau2 --agent tool_calling
./evaluate-benchmark.sh --benchmark gsm8k --agent tool_calling --phoenix-otel
```

When [`--phoenix-otel`](exgentic_a2a_runner/evaluate-benchmark.sh) is enabled, the script:
- port-forwards the Phoenix OTLP service from `kagenti-system/phoenix` to `localhost:4317`
- verifies cluster reachability early using [`kubectl cluster-info`](exgentic_a2a_runner/evaluate-benchmark.sh:109)
- exports:
  - `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317`
  - `OTEL_EXPORTER_OTLP_PROTOCOL=grpc`
  - `OTEL_EXPORTER_OTLP_INSECURE=true`

To open the Phoenix UI from your host:
```bash
kubectl port-forward -n kagenti-system svc/phoenix 6006:6006
```

Then browse to:
```text
http://localhost:6006
```

If you want both UI access and OTLP ingest at the same time:
```bash
kubectl port-forward -n kagenti-system svc/phoenix 6006:6006 4317:4317
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

### Using Phoenix in the kind Cluster

The Kagenti cluster already exposes a Phoenix service in the `kagenti-system` namespace.

#### 1. Send runner telemetry to Phoenix

Use [`--phoenix-otel`](exgentic_a2a_runner/evaluate-benchmark.sh) so the script automatically port-forwards Phoenix OTLP and configures the required environment variables:

```bash
env MAX_TASKS=1 MAX_PARALLEL_SESSIONS=1 ./evaluate-benchmark.sh --benchmark gsm8k --agent tool_calling --phoenix-otel
```

This forwards Phoenix OTLP gRPC to `localhost:4317` and exports telemetry before launching the runner.

#### 2. Open the Phoenix UI

```bash
kubectl port-forward -n kagenti-system svc/phoenix 6006:6006
```

Then open:
- **Phoenix UI**: `http://localhost:6006`
- **Phoenix GraphQL**: `http://localhost:6006/graphql`

#### 3. Recover kind access if the cluster becomes unreachable

If [`kubectl cluster-info`](exgentic_a2a_runner/evaluate-benchmark.sh:109) fails with `connection refused` while using the `kind-kagenti` context, the underlying Podman-backed kind control-plane container may be stopped.

Check the cluster runtime:
```bash
kind get clusters
podman ps -a | grep kagenti-control-plane
```

If the control-plane container is exited, restore it with:
```bash
podman machine stop podman-machine-default || true
podman machine start podman-machine-default
podman start kagenti-control-plane
kubectl cluster-info
```

In the observed failure, the control-plane container had exited and starting [`kagenti-control-plane`](exgentic_a2a_runner/evaluate-benchmark.sh) restored access immediately.
```

### Analyzing Traces with analyze-run.sh

The [`analyze-run.sh`](exgentic_a2a_runner/analyze-run.sh) script provides comprehensive trace analysis by downloading Agent.Session traces from Phoenix and generating detailed performance reports.

#### Features

- **Automatic Phoenix connectivity**: Connects to Phoenix GraphQL API with optional auto port-forwarding
- **Trace filtering**: Downloads Agent.Session root spans and all child spans
- **Performance metrics**: Calculates timing statistics (avg, p50, p95, min, max) for:
  - Session creation time
  - Agent call time (end-to-end agent execution)
  - Evaluation time
  - LLM call time and token usage
  - Tool call time
- **Grouping**: Groups traces by agent, benchmark, model, and parallel session count
- **Detailed reports**: Generates both summary statistics and individual trace details

#### Usage

```bash
# Basic usage (assumes Phoenix is accessible at localhost:6006)
./analyze-run.sh

# With custom Phoenix URL and limit
./analyze-run.sh --url http://localhost:6006/graphql --limit 200

# Auto port-forward from kind cluster if Phoenix is not accessible locally
./analyze-run.sh --forward --limit 50

# Specify a different Phoenix project
./analyze-run.sh --project my-project --limit 100
```

#### Options

| Option | Description | Default |
|--------|-------------|---------|
| `-u, --url URL` | Phoenix GraphQL endpoint URL | `http://localhost:6006/graphql` |
| `-l, --limit NUM` | Maximum number of traces to download | `100` |
| `-p, --project NAME` | Phoenix project name | `default` |
| `-f, --forward` | Auto port-forward Phoenix from kind cluster if not accessible | `false` |
| `-h, --help` | Show help message | - |

#### How It Works

1. **Connectivity Test**: Attempts to connect to Phoenix GraphQL API
2. **Auto Port-Forward** (if `--forward` is used): Sets up port-forwarding from kind cluster if Phoenix is not accessible
3. **Project Resolution**: Resolves the Phoenix project ID from the project name
4. **Trace Discovery**: Queries for Agent.Session root spans, sorted by creation time (most recent first)
5. **Full Trace Download**: For each trace ID, downloads all child spans (limited to 500 spans per trace)
6. **Analysis**: Pipes trace data to [`analyze_traces.py`](exgentic_a2a_runner/analyze_traces.py) for detailed analysis

#### Report Output

The script generates two main sections:

**1. Summary Statistics by Configuration**

Groups traces by (agent, benchmark, model, parallel sessions) and shows:
- Count of traces
- Average, P50, P95, Min, Max for:
  - Session creation time
  - Agent call time
  - Evaluation time
  - LLM call time (with token counts)
  - Tool call time
- Time distribution percentages (LLM%, Tool%, Other%)

**2. Individual Trace Details**

Lists each trace with:
- Trace ID
- Agent, Benchmark, Model, Parallel sessions
- Session creation time
- Agent call time (with LLM% and Tool% breakdown)
- Evaluation time
- LLM tokens (input/output)
- Tool call count and time

#### Example Output

```
=== Phoenix Trace Analysis ===
Phoenix URL: http://localhost:6006/graphql
Project: default
Limit: 100

✓ Connected to Phoenix (project: default, id: UHJvamVjdDox)

Found 45 Agent.Session traces
Downloading full traces with child spans...
Downloaded 45 traces

=== Trace Analysis Report ===

Summary Statistics by Configuration:
┌─────────────┬───────────┬─────────┬──────────┬───────┬─────────────┬─────────────┬─────────────┬─────────────┬─────────────┐
│ Agent       │ Benchmark │ Model   │ Parallel │ Count │ Avg Create  │ Avg Agent   │ Avg Eval    │ Avg LLM     │ Avg Tool    │
│             │           │         │          │       │ (ms)        │ Call (ms)   │ (ms)        │ (ms)        │ (ms)        │
├─────────────┼───────────┼─────────┼──────────┼───────┼─────────────┼─────────────┼─────────────┼─────────────┼─────────────┤
│ tool-calling│ gsm8k     │ gpt-4o  │ 1        │ 45    │ 125.3       │ 8234.5      │ 45.2        │ 6543.2      │ 1234.5      │
│             │           │         │          │       │             │             │             │ (79.5%)     │ (15.0%)     │
└─────────────┴───────────┴─────────┴──────────┴───────┴─────────────┴─────────────┴─────────────┴─────────────┴─────────────┘
```

#### Prerequisites

- **jq**: JSON processor for parsing GraphQL responses
  ```bash
  # macOS
  brew install jq
  
  # Ubuntu/Debian
  apt-get install jq
  ```
- **Python 3**: For running the analysis script
- **Phoenix**: Running and accessible (either locally or in kind cluster)

#### Troubleshooting

**Connection refused:**
- Ensure Phoenix is running: `kubectl get pods -n kagenti-system -l app=phoenix`
- Use `--forward` flag to auto port-forward from kind cluster
- Manually port-forward: `kubectl port-forward -n kagenti-system svc/phoenix 6006:6006`

**No traces found:**
- Verify traces exist in Phoenix UI: `http://localhost:6006`
- Check that Agent.Session spans are being created by the runner
- Ensure OTEL is enabled in the runner configuration

**GraphQL errors:**
- Check Phoenix version compatibility
- Verify the project name exists: `./analyze-run.sh` will list available projects on error

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