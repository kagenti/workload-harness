# Quick Start Guide - Running Against Kagenti Cluster

## Prerequisites

✅ kubectl configured with `kind-kagenti` context  
✅ Services running in team1 namespace:
- `exgentic-mcp-tau2-mcp` on port 8000
- `generic-agent2` on port 8080

## Quick Run

The easiest way to run the harness is using the provided script:

```bash
cd exgentic_a2a_runner
./run-with-port-forward.sh
```

This script will:
1. Set up port forwarding to both services
2. Test connectivity
3. Run the harness with verbose logging
4. Clean up port forwards on exit

## Manual Run

If you prefer to set up port forwarding manually:

### Terminal 1: Port Forward MCP Server
```bash
kubectl port-forward -n team1 svc/exgentic-mcp-tau2-mcp 8000:8000
```

### Terminal 2: Port Forward A2A Agent
```bash
kubectl port-forward -n team1 svc/generic-agent2 8080:8080
```

### Terminal 3: Run Harness
```bash
cd exgentic_a2a_runner
source .venv/bin/activate
uv run exgentic-a2a-runner --verbose
```

## Configuration

The `.env` file is already configured for the Kagenti cluster:

```bash
EXGENTIC_MCP_SERVER_URL=http://localhost:8000
A2A_BASE_URL=http://localhost:8080
MAX_TASKS=3  # Start with 3 sessions for testing
LOG_PROMPT=1  # Enable prompt logging
LOG_RESPONSE=1  # Enable response logging
```

## What to Expect

The harness will:
1. Connect to the MCP server and create a session
2. Get a task from the Tau-Bench benchmark
3. Build a prompt with the session_id
4. Send the prompt to the generic-agent2 via A2A
5. Wait for the agent to complete the task
6. Evaluate the session via MCP
7. Close the session
8. Print statistics

### Expected Output

```
2026-03-17 18:52:00 - INFO - Initializing runner components
2026-03-17 18:52:00 - INFO - Initializing OpenTelemetry instrumentation
2026-03-17 18:52:00 - INFO - Initializing Exgentic adapter
2026-03-17 18:52:01 - INFO - Creating new session
2026-03-17 18:52:01 - INFO - Processing session: session_abc123
2026-03-17 18:52:05 - INFO - Session session_abc123 completed in 4523.45ms (evaluation: success)
...
============================================================
RUN SUMMARY
============================================================
Sessions Attempted:   3
Sessions Succeeded:   3
Sessions Failed:      0
Evaluation Success:   100.0%
Total Wall Time:      15.23s
Average Latency:      5076.67ms
P50 Latency:          5000.00ms
P95 Latency:          5500.00ms
============================================================
```

## Troubleshooting

### Port Forward Issues

If port forwarding fails:
```bash
# Kill existing port forwards
pkill -f "port-forward"

# Check if ports are in use
lsof -i :8000
lsof -i :8080

# Restart port forwards
kubectl port-forward -n team1 svc/exgentic-mcp-tau2-mcp 8000:8000 &
kubectl port-forward -n team1 svc/generic-agent2 8080:8080 &
```

### MCP Connection Issues

If you see "MCP client initialization failed":
- Verify the MCP server is running: `kubectl get pods -n team1 | grep exgentic`
- Check MCP server logs: `kubectl logs -n team1 -l app=exgentic-mcp-tau2-mcp`
- Test connectivity: `curl http://localhost:8000/health` (if health endpoint exists)

### A2A Connection Issues

If you see "A2A request failed":
- Verify the agent is running: `kubectl get pods -n team1 | grep generic-agent2`
- Check agent logs: `kubectl logs -n team1 -l app=generic-agent2`
- Test agent card: `curl http://localhost:8080/.well-known/agent-card.json`

### Session Evaluation Failures

If sessions complete but evaluation fails:
- Check if the agent is using the session_id correctly in its tool calls
- Review agent logs to see what tools it's calling
- Verify the agent has access to the MCP server for tool execution

## Next Steps

After successful test run:
1. Increase `MAX_TASKS` in `.env` for longer runs
2. Enable OTLP exporter for telemetry collection
3. Run with different benchmarks by changing the MCP server
4. Analyze results and agent performance

## Support

For issues:
- Check logs with `--verbose` flag
- Review agent and MCP server logs in Kubernetes
- See main README.md for detailed documentation