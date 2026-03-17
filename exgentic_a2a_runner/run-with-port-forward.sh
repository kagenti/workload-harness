#!/bin/bash
# Helper script to set up port forwarding and run the Exgentic A2A Runner

set -e

echo "=========================================="
echo "Exgentic A2A Runner - Port Forward Setup"
echo "=========================================="
echo ""

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "Error: kubectl is not installed or not in PATH"
    exit 1
fi

# Check if we're connected to the right cluster
CURRENT_CONTEXT=$(kubectl config current-context)
echo "Current kubectl context: $CURRENT_CONTEXT"

if [ "$CURRENT_CONTEXT" != "kind-kagenti" ]; then
    echo "Warning: Not connected to kind-kagenti cluster"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "Setting up port forwarding..."
echo "  - MCP Server: localhost:8000 -> exgentic-mcp-tau2-mcp.team1:8000"
echo "  - A2A Agent:  localhost:8080 -> generic-agent2.team1:8080"
echo ""

# Kill any existing port-forwards on these ports
echo "Cleaning up existing port-forwards..."
pkill -f "port-forward.*exgentic-mcp-tau2-mcp" 2>/dev/null || true
pkill -f "port-forward.*generic-agent2" 2>/dev/null || true
sleep 2

# Start port forwarding in background
echo "Starting port-forward for MCP server..."
kubectl port-forward -n team1 svc/exgentic-mcp-tau2-mcp 8000:8000 &
PF_MCP_PID=$!

echo "Starting port-forward for A2A agent..."
kubectl port-forward -n team1 svc/generic-agent2 8080:8080 &
PF_AGENT_PID=$!

# Wait for port forwards to be ready
echo "Waiting for port forwards to be ready..."
sleep 3

# Check if port forwards are working
if ! ps -p $PF_MCP_PID > /dev/null; then
    echo "Error: MCP port-forward failed to start"
    exit 1
fi

if ! ps -p $PF_AGENT_PID > /dev/null; then
    echo "Error: Agent port-forward failed to start"
    kill $PF_MCP_PID 2>/dev/null || true
    exit 1
fi

echo ""
echo "✓ Port forwarding established"
echo "  MCP Server PID: $PF_MCP_PID"
echo "  A2A Agent PID:  $PF_AGENT_PID"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Cleaning up port forwards..."
    kill $PF_MCP_PID 2>/dev/null || true
    kill $PF_AGENT_PID 2>/dev/null || true
    echo "Done."
}

trap cleanup EXIT INT TERM

# Test connectivity
echo "Testing connectivity..."
echo -n "  MCP Server: "
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null | grep -q "200\|404"; then
    echo "✓ Reachable"
else
    echo "⚠ May not be reachable (this might be OK if no /health endpoint)"
fi

echo -n "  A2A Agent:  "
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/.well-known/agent-card.json 2>/dev/null | grep -q "200\|404"; then
    echo "✓ Reachable"
else
    echo "⚠ May not be reachable (this might be OK)"
fi

echo ""
echo "=========================================="
echo "Starting Exgentic A2A Runner"
echo "=========================================="
echo ""

# Change to the script directory
cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Installing dependencies..."
    uv sync --python 3.12
fi

# Activate virtual environment and run
source .venv/bin/activate

# Load environment variables
if [ -f ".env" ]; then
    echo "Loading environment variables from .env"
    export $(cat .env | grep -v '^#' | xargs)
    echo ""
fi

# Run the harness
echo "Running: uv run exgentic-a2a-runner --verbose"
echo ""
uv run exgentic-a2a-runner --verbose

# Cleanup will happen automatically via trap

# Made with Bob
