# Exgentic A2A Runner - Architecture Diagram

## System Architecture

```mermaid
graph TB
    subgraph "Exgentic A2A Runner"
        Runner[Runner<br/>Main Orchestrator]
        ExgenticAdapter[Exgentic Adapter<br/>Session Management]
        MCPClient[MCP Client<br/>MCP Protocol]
        A2AClient[A2A Client<br/>A2A Protocol]
        PromptBuilder[Prompt Builder<br/>Task Formatting]
        OTEL[OTEL Instrumentation<br/>Telemetry]
        Config[Configuration<br/>Environment Variables]
    end
    
    subgraph "External Services"
        ExgenticMCP[Exgentic MCP Server<br/>Benchmark Provider]
        KagentiAgent[Kagenti Agent<br/>A2A Endpoint]
        OTELCollector[OTEL Collector<br/>Telemetry Backend]
    end
    
    Runner --> Config
    Runner --> ExgenticAdapter
    Runner --> A2AClient
    Runner --> PromptBuilder
    Runner --> OTEL
    
    ExgenticAdapter --> MCPClient
    MCPClient --> ExgenticMCP
    A2AClient --> KagentiAgent
    OTEL --> OTELCollector
    
    style Runner fill:#e1f5ff
    style ExgenticAdapter fill:#fff4e1
    style MCPClient fill:#ffe1f5
    style A2AClient fill:#e1ffe1
    style ExgenticMCP fill:#ffcccc
    style KagentiAgent fill:#ccffcc
```

## Sequence Diagram - Session Processing

```mermaid
sequenceDiagram
    participant Runner
    participant ExgenticAdapter
    participant MCPClient
    participant ExgenticMCP
    participant PromptBuilder
    participant A2AClient
    participant KagentiAgent
    participant OTEL

    Runner->>OTEL: Start session span
    Runner->>ExgenticAdapter: create_session()
    ExgenticAdapter->>MCPClient: call_tool("create_session")
    MCPClient->>ExgenticMCP: MCP Request: create_session
    ExgenticMCP-->>MCPClient: {session_id, task}
    MCPClient-->>ExgenticAdapter: SessionData
    ExgenticAdapter-->>Runner: SessionData(session_id, task)
    
    Runner->>PromptBuilder: build_prompt(task, session_id)
    PromptBuilder-->>Runner: formatted_prompt
    
    Runner->>A2AClient: send_prompt(prompt)
    A2AClient->>KagentiAgent: A2A Request
    KagentiAgent-->>A2AClient: Response
    A2AClient-->>Runner: response_text
    
    Runner->>ExgenticAdapter: evaluate_session(session_id)
    ExgenticAdapter->>MCPClient: call_tool("evaluate_session", {session_id})
    MCPClient->>ExgenticMCP: MCP Request: evaluate_session
    ExgenticMCP-->>MCPClient: {success: true/false}
    MCPClient-->>ExgenticAdapter: evaluation_result
    ExgenticAdapter-->>Runner: success
    
    Runner->>ExgenticAdapter: close_session(session_id)
    ExgenticAdapter->>MCPClient: call_tool("close_session", {session_id})
    MCPClient->>ExgenticMCP: MCP Request: close_session
    ExgenticMCP-->>MCPClient: OK
    MCPClient-->>ExgenticAdapter: closed
    ExgenticAdapter-->>Runner: done
    
    Runner->>OTEL: Record metrics & end span
```

## Component Interaction Flow

```mermaid
flowchart LR
    A[Start] --> B[Load Config]
    B --> C[Initialize Components]
    C --> D{More Tasks?}
    D -->|Yes| E[Create Session]
    E --> F[Get Task & Session ID]
    F --> G[Build Prompt with Session ID]
    G --> H[Send to Agent via A2A]
    H --> I[Wait for Response]
    I --> J[Evaluate Session]
    J --> K[Close Session]
    K --> L[Record Statistics]
    L --> D
    D -->|No| M[Print Summary]
    M --> N[Shutdown OTEL]
    N --> O[End]
    
    style E fill:#ffe1e1
    style J fill:#e1ffe1
    style K fill:#e1e1ff
```

## Data Flow

```mermaid
graph LR
    subgraph "Input"
        ENV[Environment Variables]
    end
    
    subgraph "Processing"
        CONFIG[Configuration]
        SESSION[Session Data]
        PROMPT[Formatted Prompt]
        RESPONSE[Agent Response]
        EVAL[Evaluation Result]
    end
    
    subgraph "Output"
        STATS[Statistics]
        TELEMETRY[Telemetry Data]
        SUMMARY[Console Summary]
    end
    
    ENV --> CONFIG
    CONFIG --> SESSION
    SESSION --> PROMPT
    PROMPT --> RESPONSE
    RESPONSE --> EVAL
    EVAL --> STATS
    STATS --> SUMMARY
    STATS --> TELEMETRY
```

## Key Design Decisions

### 1. MCP Client Implementation
- **Decision**: Use official MCP Python SDK
- **Rationale**: Avoid reinventing the wheel, leverage maintained library
- **Trade-off**: Additional dependency vs. implementation effort

### 2. Session Lifecycle
- **Decision**: Explicit create → evaluate → close pattern
- **Rationale**: Matches Exgentic MCP server design, clear resource management
- **Trade-off**: More API calls vs. cleaner separation of concerns

### 3. Sequential Execution
- **Decision**: Process one session at a time (MVP)
- **Rationale**: Simpler implementation, easier debugging, matches appworld_a2a_runner
- **Future**: Can add parallel execution later

### 4. Prompt Format
- **Decision**: Include session_id explicitly in prompt
- **Rationale**: Agent needs to know which session to use for tool calls
- **Format**: Clear instruction to use session_id in all interactions

### 5. Configuration
- **Decision**: Environment variables for all configuration
- **Rationale**: Matches appworld_a2a_runner pattern, easy deployment
- **Trade-off**: No config file support vs. simplicity

## Error Handling Strategy

```mermaid
graph TD
    A[Operation] --> B{Success?}
    B -->|Yes| C[Continue]
    B -->|No| D{Retry?}
    D -->|Yes| E[Retry with Backoff]
    E --> A
    D -->|No| F[Log Error]
    F --> G[Record Failure Metric]
    G --> H{Abort on Failure?}
    H -->|Yes| I[Exit]
    H -->|No| J[Continue Next Task]
```

## Telemetry Strategy

### Spans Hierarchy
```
exgentic_a2a.session
├── exgentic_a2a.mcp.create_session
├── exgentic_a2a.prompt.build
├── exgentic_a2a.a2a.send_prompt
│   └── HTTP spans (auto-instrumented)
├── exgentic_a2a.mcp.evaluate_session
└── exgentic_a2a.mcp.close_session
```

### Metrics
- **Counters**: sessions_total, errors_total
- **Histograms**: session_latency_ms, evaluation_latency_ms, creation_latency_ms
- **Gauges**: inflight_sessions

### Attributes
- `exgentic.session_id`
- `exgentic.mcp_server_url`
- `exgentic.evaluation_result`
- `a2a.base_url`
- `task.status`