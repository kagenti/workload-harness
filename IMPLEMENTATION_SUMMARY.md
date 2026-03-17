# Exgentic A2A Runner - Implementation Summary

## Project Overview

The `exgentic_a2a_runner` is a test harness that integrates Exgentic benchmarks with Kagenti agents using the A2A protocol. It follows the execution model defined in [GitHub Issue #963](https://github.com/kagenti/kagenti/issues/963).

## What We're Building

A standalone Python runner that:
1. Connects to an Exgentic MCP server to get benchmark tasks
2. Creates isolated sessions for each task
3. Sends tasks to Kagenti agents via A2A protocol
4. Evaluates agent performance using the MCP server
5. Collects comprehensive telemetry data
6. Provides detailed statistics and reporting

## Key Design Principles

### 1. **Modular Architecture**
- Clear separation of concerns (MCP, A2A, OTEL, Config)
- Reusable components from `appworld_a2a_runner`
- Easy to test and maintain

### 2. **Sequential Execution (MVP)**
- One session at a time for simplicity
- Easier debugging and monitoring
- Can be extended to parallel execution later

### 3. **Explicit Session Lifecycle**
```
CREATE → USE → EVALUATE → CLOSE
```

### 4. **Configuration-Driven**
- All settings via environment variables
- No code changes needed for different deployments
- Easy integration with CI/CD

### 5. **Comprehensive Observability**
- OpenTelemetry for traces, metrics, and logs
- Detailed session-level tracking
- Performance analytics

## File Structure

```
exgentic_a2a_runner/
├── pyproject.toml                    # Dependencies: mcp, requests, opentelemetry
├── README.md                         # User documentation
├── example.env                       # Configuration template
├── .gitignore                        # Git ignore patterns
└── exgentic_a2a_runner/
    ├── __init__.py                   # Package init
    ├── config.py                     # Config classes (ExgenticConfig, A2AConfig, etc.)
    ├── mcp_client.py                 # MCP SDK wrapper
    ├── exgentic_adapter.py           # Session lifecycle management
    ├── a2a_client.py                 # A2A protocol client (from appworld)
    ├── prompt.py                     # Prompt builder with session_id
    ├── otel.py                       # OpenTelemetry instrumentation
    └── runner.py                     # Main orchestration logic
```

## Core Components

### 1. MCPClient (`mcp_client.py`)
**Purpose**: Communicate with Exgentic MCP server using official SDK

**Key Methods**:
- `initialize()`: Connect to MCP server
- `call_tool(name, arguments)`: Generic tool invocation
- `create_session()`: Create new benchmark session
- `evaluate_session(session_id)`: Evaluate session success
- `close_session(session_id)`: Cleanup session
- `shutdown()`: Close connection

### 2. ExgenticAdapter (`exgentic_adapter.py`)
**Purpose**: High-level interface to Exgentic operations

**Key Methods**:
- `initialize()`: Setup MCP client
- `create_session() -> SessionData`: Create and return session info
- `evaluate_session(session_id) -> bool`: Get evaluation result
- `close_session(session_id)`: Close session
- `iterate_sessions()`: Iterator for sequential processing

**SessionData Class**:
```python
@dataclass
class SessionData:
    session_id: str
    task: str
    created_at: float
```

### 3. Prompt Builder (`prompt.py`)
**Purpose**: Format tasks with session_id for agent

**Format**:
```
The task you are to complete is:
{task}

IMPORTANT: Use session id "{session_id}" in all your interactions with the benchmark tools.
```

### 4. Runner (`runner.py`)
**Purpose**: Main orchestration following execution model

**Process Flow**:
```python
for session_data in exgentic_adapter.iterate_sessions():
    start_time = time.time()
    
    # Build prompt with session_id
    prompt = build_prompt(session_data.task, session_data.session_id)
    
    # Send to agent
    response = a2a_client.send_prompt(prompt)
    
    # Evaluate
    success = exgentic_adapter.evaluate_session(session_data.session_id)
    
    # Close
    exgentic_adapter.close_session(session_data.session_id)
    
    # Record stats
    completion_time = time.time() - start_time
    stats[session_id] = (completion_time, success)
```

## Configuration

### Required Environment Variables
```bash
EXGENTIC_MCP_SERVER_URL=http://localhost:3000  # MCP server endpoint
A2A_BASE_URL=http://localhost:8000             # Kagenti agent endpoint
```

### Optional Environment Variables
```bash
# Exgentic Configuration
EXGENTIC_MCP_TIMEOUT_SECONDS=60
MAX_TASKS=10
ABORT_ON_FAILURE=false

# A2A Configuration
A2A_TIMEOUT_SECONDS=300
A2A_AUTH_TOKEN=
A2A_VERIFY_TLS=true
A2A_ENDPOINT_PATH=/v1/chat

# OpenTelemetry
OTEL_SERVICE_NAME=exgentic-a2a-runner
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc

# Debug
LOG_PROMPT=0
LOG_RESPONSE=0
```

## Dependencies

```toml
dependencies = [
    "mcp>=0.9.0",                                    # MCP protocol
    "requests>=2.28.0",                              # HTTP client
    "opentelemetry-api>=1.20.0",                     # OTEL API
    "opentelemetry-sdk>=1.20.0",                     # OTEL SDK
    "opentelemetry-exporter-otlp>=1.20.0",          # OTEL exporter
    "opentelemetry-instrumentation-requests>=0.41b0", # HTTP instrumentation
]
```

## Telemetry

### Traces
- `exgentic_a2a.session`: Overall session processing
- `exgentic_a2a.mcp.create_session`: Session creation
- `exgentic_a2a.prompt.build`: Prompt construction
- `exgentic_a2a.a2a.send_prompt`: Agent invocation
- `exgentic_a2a.mcp.evaluate_session`: Evaluation
- `exgentic_a2a.mcp.close_session`: Cleanup

### Metrics
- `exgentic_a2a_sessions_total{status=success|failed}`
- `exgentic_a2a_session_latency_ms`
- `exgentic_a2a_evaluation_latency_ms`
- `exgentic_a2a_session_creation_latency_ms`
- `exgentic_a2a_inflight_sessions`

### Attributes
- `exgentic.session_id`
- `exgentic.mcp_server_url`
- `exgentic.evaluation_result`
- `a2a.base_url`
- `task.status`

## Usage

```bash
# Install
cd exgentic_a2a_runner
uv sync --python 3.12
source .venv/bin/activate

# Configure
cp example.env .env
# Edit .env with your settings

# Run
uv run exgentic-a2a-runner
```

## Output

### Console Summary
```
============================================================
RUN SUMMARY
============================================================
Sessions Attempted:   100
Sessions Succeeded:   95
Sessions Failed:      5
Total Wall Time:      1234.56s
Average Latency:      12345.67ms
P50 Latency:          10000.00ms
P95 Latency:          20000.00ms
Success Rate:         95.00%
============================================================
```

## Differences from AppWorld Runner

| Aspect | AppWorld Runner | Exgentic Runner |
|--------|----------------|-----------------|
| **Task Source** | AppWorld dataset enumeration | MCP server `create_session` |
| **Protocol** | Direct AppWorld API | MCP protocol |
| **Session Management** | Implicit (AppWorld context) | Explicit (create/close) |
| **Evaluation** | AppWorld evaluation system | MCP `evaluate_session` |
| **Prompt Format** | Task + supervisor + apps | Task + session_id |
| **Dependencies** | `appworld` package | `mcp` package |

## Implementation Checklist

- [x] Architecture design
- [x] Component specifications
- [x] Configuration design
- [x] Telemetry design
- [ ] Create directory structure
- [ ] Implement MCPClient
- [ ] Implement ExgenticAdapter
- [ ] Implement prompt builder
- [ ] Implement Runner
- [ ] Reuse/adapt A2A client
- [ ] Add OTEL instrumentation
- [ ] Create configuration files
- [ ] Write README
- [ ] Test with real services

## Next Steps

1. **Review & Approve Plan**: Ensure design meets requirements
2. **Switch to Code Mode**: Begin implementation
3. **Implement Core Components**: MCPClient, ExgenticAdapter, Runner
4. **Add Telemetry**: OTEL instrumentation
5. **Create Documentation**: README, examples
6. **Test Integration**: With real Exgentic MCP server and Kagenti agent
7. **Iterate**: Based on testing feedback

## Success Criteria

✅ Sequential execution of benchmark tasks via MCP server  
✅ Proper session lifecycle management (create → evaluate → close)  
✅ Integration with Kagenti agents via A2A protocol  
✅ Session_id included in prompts for agent use  
✅ Comprehensive OpenTelemetry instrumentation  
✅ Configuration via environment variables  
✅ Summary statistics and reporting  
✅ Proper error handling and logging  

## Questions?

If you have any questions or need clarification on any aspect of the design, please ask before we proceed to implementation!