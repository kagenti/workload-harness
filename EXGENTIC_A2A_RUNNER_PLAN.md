# Exgentic A2A Runner - Implementation Plan

## Overview

Create a test harness called `exgentic_a2a_runner` that integrates Exgentic benchmarks with Kagenti agents using the A2A protocol. This harness will follow the execution model defined in [GitHub Issue #963](https://github.com/kagenti/kagenti/issues/963).

## Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     Exgentic A2A Runner                         │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    │
│  │   Runner     │───▶│   Exgentic   │───▶│  MCP Client  │    │
│  │              │    │   Adapter    │    │              │    │
│  └──────────────┘    └──────────────┘    └──────────────┘    │
│         │                    │                    │            │
│         │                    │                    ▼            │
│         │                    │            ┌──────────────┐    │
│         │                    │            │ Exgentic MCP │    │
│         │                    │            │   Server     │    │
│         │                    │            └──────────────┘    │
│         │                    │                                 │
│         ▼                    ▼                                 │
│  ┌──────────────┐    ┌──────────────┐                        │
│  │  A2A Client  │    │    Prompt    │                        │
│  │              │    │   Builder    │                        │
│  └──────────────┘    └──────────────┘                        │
│         │                                                      │
│         ▼                                                      │
│  ┌──────────────┐                                             │
│  │ Kagenti Agent│                                             │
│  │  (via A2A)   │                                             │
│  └──────────────┘                                             │
└─────────────────────────────────────────────────────────────────┘
```

### Execution Model (from Issue #963)

For each task:
1. **Create Session**: `(session_id, task) = benchmark_mcp.call("create_session")`
2. **Record Start Time**: `startTime = time()`
3. **Invoke Agent**: `agent.invoke_agent("{task}. Use session id {session_id} in all accesses")`
4. **Record Completion Time**: `completionTime = time() - startTime`
5. **Evaluate Session**: `success = benchmark_mcp.call("evaluate_session", {"session_id": session_id})`
6. **Store Statistics**: `stats[session_id] = (completion_time, success)`
7. **Close Session**: `benchmark_mcp.call("close_session", {"session_id": session_id})`

## Directory Structure

```
exgentic_a2a_runner/
├── pyproject.toml              # Project configuration and dependencies
├── README.md                   # Documentation
├── example.env                 # Example environment configuration
├── .gitignore                  # Git ignore patterns
└── exgentic_a2a_runner/
    ├── __init__.py            # Package initialization
    ├── runner.py              # Main orchestration logic
    ├── config.py              # Configuration management
    ├── exgentic_adapter.py    # Exgentic MCP server adapter
    ├── mcp_client.py          # MCP protocol client
    ├── a2a_client.py          # A2A protocol client (reused from appworld)
    ├── prompt.py              # Prompt construction
    └── otel.py                # OpenTelemetry instrumentation
```

## Component Details

### 1. Configuration (`config.py`)

**ExgenticConfig**
- `mcp_server_url`: URL of the Exgentic MCP server (required)
- `mcp_timeout_seconds`: Timeout for MCP operations (default: 60)
- `max_tasks`: Maximum number of tasks to process (optional)
- `abort_on_failure`: Stop on first failure (default: false)

**A2AConfig** (reused from appworld_a2a_runner)
- `base_url`: A2A endpoint base URL
- `timeout_seconds`: Request timeout
- `auth_token`: Bearer token for authentication
- `verify_tls`: TLS verification flag
- `endpoint_path`: Endpoint path

**OTELConfig** (reused from appworld_a2a_runner)
- Standard OpenTelemetry configuration

**DebugConfig** (reused from appworld_a2a_runner)
- `log_prompt`: Log prompt details
- `log_response`: Log response details

### 2. MCP Client (`mcp_client.py`)

Uses the official MCP Python SDK to communicate with the Exgentic MCP server.

**Key Methods:**
- `create_session() -> (session_id: str, task: str)`: Create a new benchmark session
- `evaluate_session(session_id: str) -> bool`: Evaluate session success
- `close_session(session_id: str) -> None`: Close and cleanup session

**Implementation Notes:**
- Use `mcp` Python package for MCP protocol communication
- Handle connection lifecycle properly
- Implement proper error handling and timeouts
- Support both stdio and SSE transport modes

### 3. Exgentic Adapter (`exgentic_adapter.py`)

Provides high-level interface to Exgentic MCP server operations.

**SessionData Class:**
```python
class SessionData:
    session_id: str
    task: str
    created_at: float
```

**ExgenticAdapter Class:**
- `initialize()`: Initialize MCP client connection
- `create_session() -> SessionData`: Create new session and get task
- `evaluate_session(session_id: str) -> bool`: Evaluate session
- `close_session(session_id: str)`: Close session
- `iterate_sessions()`: Iterator for sequential session processing

### 4. Prompt Builder (`prompt.py`)

Constructs prompts that include the session_id for the agent.

**Format:**
```
The task you are to complete is:
{task}

IMPORTANT: Use session id "{session_id}" in all your interactions with the benchmark tools.
```

### 5. A2A Client (`a2a_client.py`)

Reuse the existing implementation from `appworld_a2a_runner` with minimal modifications.

### 6. Runner (`runner.py`)

Main orchestration logic following the execution model.

**SessionResult Class:**
```python
class SessionResult:
    session_id: str
    success: bool
    latency_ms: float
    error: Optional[str]
    response_chars: Optional[int]
```

**Runner Class:**
- `initialize()`: Initialize all components
- `process_session(session_data: SessionData) -> SessionResult`: Process single session
- `run() -> int`: Main execution loop

**Process Flow:**
```python
def process_session(session_data):
    start_time = time.time()
    
    # Build prompt with session_id
    prompt = build_prompt(session_data.task, session_data.session_id)
    
    # Send to agent via A2A
    response = a2a_client.send_prompt(prompt)
    
    # Evaluate session
    success = exgentic_adapter.evaluate_session(session_data.session_id)
    
    # Close session
    exgentic_adapter.close_session(session_data.session_id)
    
    completion_time = time.time() - start_time
    
    return SessionResult(
        session_id=session_data.session_id,
        success=success,
        latency_ms=completion_time * 1000,
        response_chars=len(response)
    )
```

### 7. OpenTelemetry Instrumentation (`otel.py`)

Extended from appworld_a2a_runner with additional metrics.

**Additional Spans:**
- `exgentic_a2a.session`: Overall session processing
- `exgentic_a2a.mcp.create_session`: Session creation
- `exgentic_a2a.mcp.evaluate_session`: Session evaluation
- `exgentic_a2a.mcp.close_session`: Session cleanup

**Additional Attributes:**
- `exgentic.session_id`: Session identifier
- `exgentic.mcp_server_url`: MCP server URL
- `exgentic.evaluation_result`: Success/failure of evaluation

**Additional Metrics:**
- `exgentic_a2a_sessions_total{status=success|failed}`: Total sessions processed
- `exgentic_a2a_session_latency_ms`: End-to-end session latency
- `exgentic_a2a_evaluation_latency_ms`: Evaluation operation latency
- `exgentic_a2a_session_creation_latency_ms`: Session creation latency

## Configuration Files

### pyproject.toml

```toml
[project]
name = "exgentic-a2a-runner"
version = "0.1.0"
description = "Exgentic Benchmark A2A Runner for Kagenti"
requires-python = ">=3.11"
dependencies = [
    "mcp>=0.9.0",
    "requests>=2.28.0",
    "opentelemetry-api>=1.20.0",
    "opentelemetry-sdk>=1.20.0",
    "opentelemetry-exporter-otlp>=1.20.0",
    "opentelemetry-instrumentation-requests>=0.41b0",
]

[project.scripts]
exgentic-a2a-runner = "exgentic_a2a_runner.runner:main"
```

### example.env

```bash
# REQUIRED CONFIGURATION
EXGENTIC_MCP_SERVER_URL=http://localhost:3000
A2A_BASE_URL=http://localhost:8000

# OPTIONAL CONFIGURATION
EXGENTIC_MCP_TIMEOUT_SECONDS=60
MAX_TASKS=10
ABORT_ON_FAILURE=false

# A2A Configuration
A2A_TIMEOUT_SECONDS=300
A2A_AUTH_TOKEN=
A2A_VERIFY_TLS=true
A2A_ENDPOINT_PATH=/v1/chat

# OpenTelemetry Configuration
OTEL_SERVICE_NAME=exgentic-a2a-runner
OTEL_EXPORTER_OTLP_ENDPOINT=
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_INSTRUMENT_REQUESTS=true

# Debug Configuration
LOG_PROMPT=0
LOG_RESPONSE=0
```

## Key Differences from AppWorld Runner

1. **MCP Integration**: Uses MCP protocol instead of direct AppWorld API calls
2. **Session Management**: Explicit session lifecycle (create → use → evaluate → close)
3. **Task Source**: Tasks come from MCP server's `create_session` call, not from dataset enumeration
4. **Evaluation**: Uses MCP server's `evaluate_session` instead of AppWorld's evaluation system
5. **Prompt Format**: Includes session_id in the prompt for agent to use
6. **Dependencies**: Adds MCP Python SDK, removes AppWorld package

## Implementation Phases

### Phase 1: Core Structure ✓
- [x] Create directory structure
- [x] Set up configuration management
- [x] Create basic project files (pyproject.toml, README.md, example.env)

### Phase 2: MCP Integration
- [ ] Implement MCPClient using official MCP SDK
- [ ] Implement ExgenticAdapter with session lifecycle
- [ ] Add proper error handling and timeouts

### Phase 3: Runner Logic
- [ ] Implement main Runner class
- [ ] Implement session processing flow
- [ ] Add summary statistics and reporting

### Phase 4: Integration
- [ ] Reuse/adapt A2A client from appworld_a2a_runner
- [ ] Implement prompt builder with session_id
- [ ] Add OpenTelemetry instrumentation

### Phase 5: Testing & Documentation
- [ ] Test with actual Exgentic MCP server
- [ ] Complete README with usage examples
- [ ] Add error handling and edge cases

## Success Criteria

1. ✅ Sequential execution of benchmark tasks via MCP server
2. ✅ Proper session lifecycle management (create → evaluate → close)
3. ✅ Integration with Kagenti agents via A2A protocol
4. ✅ Session_id included in prompts for agent use
5. ✅ Comprehensive OpenTelemetry instrumentation
6. ✅ Configuration via environment variables
7. ✅ Summary statistics and reporting
8. ✅ Proper error handling and logging

## Next Steps

1. Review and approve this plan
2. Switch to Code mode to implement the solution
3. Test with actual Exgentic MCP server and Kagenti agent
4. Iterate based on testing results