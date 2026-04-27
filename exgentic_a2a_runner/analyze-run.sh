#!/bin/bash

# analyze-run.sh - Download and analyze Phoenix traces for invoke_agent spans
#
# This script connects to Phoenix via GraphQL, downloads the most recent agent traces,
# and generates a report with timing statistics.

set -e

# Default values
PHOENIX_URL="http://localhost:6006/graphql"
LIMIT=100
AUTO_PORT_FORWARD="false"
PHOENIX_NAMESPACE="kagenti-system"
PHOENIX_SERVICE="phoenix"
PHOENIX_HTTP_LOCAL_PORT="6006"
KUBECTL_BIN="${KUBECTL_BIN:-kubectl}"
PROJECT_NAME="default"

# Parse command line arguments
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Options:
    -u, --url URL              Phoenix GraphQL endpoint URL (default: http://localhost:6006/graphql)
    -l, --limit NUM            Limit number of traces to download (default: 100)
    -p, --project NAME         Phoenix project name (default: default)
    -f, --forward              Auto port-forward Phoenix from kind cluster if not accessible
    -h, --help                 Show this help message

Example:
    $0 -u http://localhost:6006/graphql -l 200
    $0 -f -l 50
EOF
    exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -u|--url)
            PHOENIX_URL="$2"
            shift 2
            ;;
        -l|--limit)
            LIMIT="$2"
            shift 2
            ;;
        -p|--project)
            PROJECT_NAME="$2"
            shift 2
            ;;
        -f|--forward)
            AUTO_PORT_FORWARD="true"
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

echo "=== Phoenix Trace Analysis ==="
echo "Phoenix URL: $PHOENIX_URL"
echo "Project: $PROJECT_NAME"
echo "Limit: $LIMIT"
echo ""

# Create temporary files
TEMP_FILE=$(mktemp)
trap "rm -f $TEMP_FILE" EXIT

# Function to run a GraphQL query
run_graphql() {
    local query="$1"
    curl -s --max-time 10 -X POST "$PHOENIX_URL" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"$query\"}" 2>&1
}

# Function to setup port forwarding
setup_port_forward() {
    echo "Setting up port forwarding to Phoenix in kind cluster..."

    if ! command -v "$KUBECTL_BIN" &> /dev/null; then
        echo "Error: $KUBECTL_BIN is not installed or not in PATH"
        return 1
    fi

    if ! CURRENT_CONTEXT=$("$KUBECTL_BIN" config current-context 2>/dev/null); then
        echo "Error: Unable to determine current kubectl context"
        return 1
    fi

    if [ "$CURRENT_CONTEXT" != "kind-kagenti" ]; then
        echo "Warning: Not connected to kind-kagenti cluster (current: $CURRENT_CONTEXT)"
        return 1
    fi

    echo "Checking if Phoenix pod is ready..."
    if ! "$KUBECTL_BIN" wait --for=condition=ready pod -l app=phoenix -n $PHOENIX_NAMESPACE --timeout=30s >/dev/null 2>&1; then
        echo "Error: Phoenix pod is not ready in cluster"
        return 1
    fi

    echo "Cleaning up existing port-forward on port ${PHOENIX_HTTP_LOCAL_PORT}..."
    lsof -ti:${PHOENIX_HTTP_LOCAL_PORT} | xargs kill -9 2>/dev/null || true
    sleep 2

    echo "Starting port-forward: localhost:${PHOENIX_HTTP_LOCAL_PORT} -> ${PHOENIX_SERVICE}.${PHOENIX_NAMESPACE}:6006"
    "$KUBECTL_BIN" port-forward -n $PHOENIX_NAMESPACE svc/$PHOENIX_SERVICE ${PHOENIX_HTTP_LOCAL_PORT}:6006 >/dev/null 2>&1 &
    PF_PHOENIX_PID=$!

    echo "Waiting for port-forward to be ready..."
    sleep 3

    if ! curl -s --max-time 2 "$PHOENIX_URL" -H "Content-Type: application/json" -d '{"query":"{ __schema { queryType { name } } }"}' >/dev/null 2>&1; then
        echo "Warning: Port-forward started but Phoenix is not responding yet"
    else
        echo "✓ Port-forward established successfully"
    fi

    return 0
}

cleanup_port_forward() {
    if [ -n "$PF_PHOENIX_PID" ]; then
        echo ""
        echo "Cleaning up port-forward (PID: $PF_PHOENIX_PID)..."
        kill $PF_PHOENIX_PID 2>/dev/null || true
    fi
}

# Step 1: Test connectivity
echo "Connecting to Phoenix..."
set +e
RESPONSE=$(run_graphql "{ projects { edges { node { id name } } } }")
CURL_EXIT=$?
set -e

if [[ $CURL_EXIT -ne 0 ]] || [[ -z "$RESPONSE" ]] || echo "$RESPONSE" | grep -q "Connection refused\|Could not resolve\|Failed to connect" 2>/dev/null; then
    if [ "$AUTO_PORT_FORWARD" = "true" ]; then
        echo "Phoenix not accessible locally, attempting to port-forward from kind cluster..."
        echo ""

        if setup_port_forward; then
            trap cleanup_port_forward EXIT

            echo ""
            echo "Retrying Phoenix connection..."
            set +e
            RESPONSE=$(run_graphql "{ projects { edges { node { id name } } } }")
            CURL_EXIT=$?
            set -e

            if [[ $CURL_EXIT -ne 0 ]] || [[ -z "$RESPONSE" ]]; then
                echo "Error: Still unable to connect to Phoenix after port-forwarding"
                exit 1
            fi
        else
            echo ""
            echo "Error: Failed to setup port-forward to Phoenix"
            exit 1
        fi
    else
        echo "Error: Failed to connect to Phoenix at $PHOENIX_URL"
        echo "Use --forward flag to auto port-forward from kind cluster"
        exit 1
    fi
fi

# Step 2: Resolve project ID
PROJECT_ID=$(echo "$RESPONSE" | jq -r ".data.projects.edges[].node | select(.name == \"$PROJECT_NAME\") | .id" 2>/dev/null)

if [[ -z "$PROJECT_ID" ]] || [[ "$PROJECT_ID" == "null" ]]; then
    echo "Error: Project '$PROJECT_NAME' not found in Phoenix"
    echo "Available projects:"
    echo "$RESPONSE" | jq -r '.data.projects.edges[].node.name' 2>/dev/null
    exit 1
fi

echo "✓ Connected to Phoenix (project: $PROJECT_NAME, id: $PROJECT_ID)"
echo ""

# Step 3: Fetch invoke_agent root spans
echo "Fetching agent traces..."

# Escape quotes for GraphQL query embedded in JSON
SPANS_QUERY="{ node(id: \\\"$PROJECT_ID\\\") { ... on Project { spans(first: $LIMIT, rootSpansOnly: true, sort: {col: startTime, dir: desc}, filterCondition: \\\"span_kind == 'AGENT'\\\") { edges { node { name spanKind statusCode statusMessage latencyMs startTime context { traceId spanId } attributes } } } } } }"

set +e
SPANS_RESPONSE=$(run_graphql "$SPANS_QUERY")
set -e

if echo "$SPANS_RESPONSE" | jq -e '.errors' > /dev/null 2>&1; then
    echo "Error: GraphQL query failed"
    echo "$SPANS_RESPONSE" | jq '.errors'
    exit 1
fi

SPAN_COUNT=$(echo "$SPANS_RESPONSE" | jq -r '.data.node.spans.edges | length' 2>/dev/null)

if [[ -z "$SPAN_COUNT" ]] || [[ "$SPAN_COUNT" == "null" ]] || [[ "$SPAN_COUNT" == "0" ]]; then
    echo "No invoke_agent traces found"
    exit 0
fi

echo "Fetched $SPAN_COUNT agent traces"
echo ""

# Step 4: Extract data from spans
# Parse attributes (JSON string) to extract agent name, model, session_id, and timing
echo "$SPANS_RESPONSE" | jq -r '
    .data.node.spans.edges[].node |
    . as $span |
    (if (.attributes | type) == "string" then (.attributes | fromjson) else .attributes end) as $attrs |
    ($attrs.gen_ai.agent.name // "unknown") as $agent |
    ($attrs.gen_ai.request.model // $attrs.llm.model_name // "unknown") as $model |
    ($attrs.gen_ai.conversation.id // "unknown") as $session_id |
    ($span.statusCode // "UNSET") as $status |
    ($span.latencyMs // 0) as $latency |
    ($span.startTime // "") as $start_time |
    "\($agent),\($model),\($status),\($latency),\($start_time),\($session_id)"
' > "$TEMP_FILE" 2>/dev/null

if [[ ! -s "$TEMP_FILE" ]]; then
    echo "No trace data could be extracted"
    exit 0
fi

# Step 5: Generate report
echo "=== Trace Analysis Report ==="
echo ""

# Summary by agent + model
printf "%-25s %-30s %-8s %-8s %-12s %-12s %-12s\n" \
    "Agent" "Model" "Traces" "Errors" "Avg(s)" "P50(s)" "P95(s)"
printf "%-25s %-30s %-8s %-8s %-12s %-12s %-12s\n" \
    "-------------------------" "------------------------------" "--------" "--------" "------------" "------------" "------------"

sort "$TEMP_FILE" | awk -F',' '
{
    key = $1 "," $2
    count[key]++
    latencies[key] = latencies[key] " " ($4 / 1000)  # ms to seconds

    if ($3 == "ERROR") {
        errors[key]++
    }

    if (!(key in seen)) {
        agent[key] = $1
        model[key] = $2
        seen[key] = 1
    }
}
END {
    for (key in count) {
        n = count[key]
        err = (key in errors) ? errors[key] : 0

        # Calculate stats from latencies
        split(latencies[key], vals, " ")
        sum = 0
        # Sort values for percentiles
        for (i in vals) {
            if (vals[i] != "") sum += vals[i]
        }
        avg = sum / n

        # Simple p50/p95 (collect non-empty values, sort)
        j = 0
        for (i in vals) {
            if (vals[i] != "") {
                j++
                sorted[j] = vals[i] + 0
            }
        }
        # Bubble sort (small N)
        for (a = 1; a <= j; a++) {
            for (b = a + 1; b <= j; b++) {
                if (sorted[a] > sorted[b]) {
                    tmp = sorted[a]; sorted[a] = sorted[b]; sorted[b] = tmp
                }
            }
        }
        p50_idx = int(j * 0.5) + 1
        if (p50_idx > j) p50_idx = j
        p50 = sorted[p50_idx]

        p95_idx = int(j * 0.95) + 1
        if (p95_idx > j) p95_idx = j
        p95 = sorted[p95_idx]

        printf "%-25s %-30s %-8d %-8d %-12.2f %-12.2f %-12.2f\n",
            agent[key], model[key], n, err, avg, p50, p95

        # Cleanup
        delete sorted
    }
}'

echo ""

# Individual trace listing
echo "=== Individual Traces ==="
echo ""
printf "%-38s %-6s %-10s %-20s\n" \
    "Session ID" "Status" "Latency(s)" "Start Time"
printf "%-38s %-6s %-10s %-20s\n" \
    "--------------------------------------" "------" "----------" "--------------------"

sort -t',' -k5 "$TEMP_FILE" | awk -F',' '{
    latency_s = $4 / 1000
    # Truncate start time
    start = $5
    gsub(/T/, " ", start)
    sub(/\.[0-9]+.*/, "", start)
    printf "%-38s %-6s %-10.2f %-20s\n", $6, $3, latency_s, start
}'

echo ""
echo "Analysis complete!"
