#!/bin/bash
# Evaluate a specific Exgentic benchmark
# Usage: ./evaluate_benchmark.sh --benchmark <name> --agent <name>
# Example: ./evaluate_benchmark.sh --benchmark tau2 --agent tool_calling

set -e

BENCHMARK_NAME=""
AGENT_NAME_INPUT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --benchmark)
            BENCHMARK_NAME="$2"
            shift 2
            ;;
        --agent)
            AGENT_NAME_INPUT="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 --benchmark <name> --agent <name>"
            echo ""
            echo "Required Arguments:"
            echo "  --benchmark NAME           Benchmark name (e.g., gsm8k, tau2)"
            echo "  --agent NAME               Agent name (e.g., tool_calling, generic_agent)"
            echo ""
            echo "Options:"
            echo "  -h, --help                 Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --benchmark tau2 --agent tool_calling"
            echo "  $0 --benchmark gsm8k --agent generic_agent"
            exit 0
            ;;
        -*)
            echo "Error: Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
        *)
            echo "Error: Unexpected argument: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

if [ -z "$BENCHMARK_NAME" ] || [ -z "$AGENT_NAME_INPUT" ]; then
    echo "Error: Both --benchmark and --agent are required"
    echo "Usage: $0 --benchmark <name> --agent <name>"
    echo "Use --help for more information"
    exit 1
fi

# Load environment variables if .env exists (before setting service names)
if [ -f "$(dirname "$0")/.env" ]; then
    source "$(dirname "$0")/.env"
fi

# Construct agent service name
if [[ "$AGENT_NAME_INPUT" == exgentic-a2a-* ]]; then
    FULL_AGENT_NAME="$AGENT_NAME_INPUT"
else
    FULL_AGENT_NAME="exgentic-a2a-${AGENT_NAME_INPUT}"
fi
# Replace underscores with hyphens for Kubernetes compatibility
export AGENT_SERVICE="${FULL_AGENT_NAME}-${BENCHMARK_NAME}"
AGENT_SERVICE="${AGENT_SERVICE//_/-}"

# Set benchmark service name (override .env values)
export BENCHMARK_SERVICE="exgentic-mcp-${BENCHMARK_NAME}-mcp"

echo "=========================================="
echo "Exgentic A2A Runner - Benchmark Evaluation"
echo "=========================================="
echo "Benchmark: $BENCHMARK_NAME"
echo "Agent Service: $AGENT_SERVICE"
echo "Benchmark Service: $BENCHMARK_SERVICE"
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
echo "  - MCP Server: localhost:7770 -> $BENCHMARK_SERVICE.team1:8000"
echo "  - A2A Agent:  localhost:7701 -> $AGENT_SERVICE.team1:8080"
echo ""

# Kill any existing port-forwards on these ports
echo "Cleaning up existing port-forwards on ports 7770 and 7701..."
# Kill any process using port 7770
lsof -ti:7770 | xargs kill -9 2>/dev/null || true
# Kill any process using port 7701
lsof -ti:7701 | xargs kill -9 2>/dev/null || true
sleep 2

# Check if pods are ready before port-forwarding
echo "Checking if pods are ready..."

# Extract deployment names (remove -mcp suffix from BENCHMARK_SERVICE if present)
BENCHMARK_DEPLOYMENT="${BENCHMARK_SERVICE%-mcp}"
AGENT_DEPLOYMENT="$AGENT_SERVICE"

# Wait for MCP server pod to be ready
echo "  Checking MCP server pod..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=$BENCHMARK_DEPLOYMENT -n team1 --timeout=60s
if [ $? -ne 0 ]; then
    echo "Error: MCP server pod is not ready"
    exit 1
fi

# Wait for agent pod to be ready
echo "  Checking agent pod..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=$AGENT_DEPLOYMENT -n team1 --timeout=60s
if [ $? -ne 0 ]; then
    echo "Error: Agent pod is not ready"
    exit 1
fi

echo "✓ All pods are ready"
echo ""

# Additional wait to ensure services are fully started
echo "Waiting for services to be fully started..."
sleep 10

# Start port forwarding in background (suppress "Handling connection" messages)
echo "Starting port-forward for MCP server..."
kubectl port-forward -n team1 svc/$BENCHMARK_SERVICE 7770:8000 >/dev/null 2>&1 &
PF_MCP_PID=$!

echo "Starting port-forward for A2A agent..."
kubectl port-forward -n team1 svc/$AGENT_SERVICE 7701:8080 >/dev/null 2>&1 &
PF_AGENT_PID=$!

# Wait for port forwards to be ready
echo "Waiting for port forwards to be ready..."
sleep 5

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
if curl -s -o /dev/null -w "%{http_code}" http://localhost:7770/health 2>/dev/null | grep -q "200\|404"; then
    echo "✓ Reachable"
else
    echo "⚠ May not be reachable - this might be OK if no /health endpoint"
fi

echo -n "  A2A Agent:  "
if curl -s -o /dev/null -w "%{http_code}" http://localhost:7701/.well-known/agent-card.json 2>/dev/null | grep -q "200\|404"; then
    echo "✓ Reachable"
else
    echo "⚠ May not be reachable - this might be OK"
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

# Set URLs for port-forwarded services (override .env if present)
export EXGENTIC_MCP_SERVER_URL="http://localhost:7770/mcp"
export A2A_BASE_URL="http://localhost:7701"

# Run the harness with optional log level
LOG_LEVEL_ARG=""
if [ -n "${LOG_LEVEL}" ]; then
    LOG_LEVEL_ARG="--log-level ${LOG_LEVEL}"
    echo "Running: uv run exgentic-a2a-runner --log-level ${LOG_LEVEL}"
else
    echo "Running: uv run exgentic-a2a-runner"
fi
echo ""
uv run exgentic-a2a-runner $LOG_LEVEL_ARG

# Cleanup will happen automatically via trap

# Made with Bob