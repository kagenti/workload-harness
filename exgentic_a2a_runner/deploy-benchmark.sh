#!/bin/bash
# Deploy Exgentic benchmark to Kagenti cluster
# Usage: ./deploy-benchmark.sh <benchmark-name> [keycloak-username] [keycloak-password]
# Example: ./deploy-benchmark.sh gsm8k admin admin

set -e

BENCHMARK_NAME="$1"
KEYCLOAK_USERNAME="${2:-admin}"
KEYCLOAK_PASSWORD="${3:-admin}"

if [ -z "$BENCHMARK_NAME" ]; then
    echo "Error: Benchmark name is required"
    echo "Usage: $0 <benchmark-name> [keycloak-username] [keycloak-password]"
    echo "Example: $0 gsm8k admin admin"
    exit 1
fi

IMAGE_NAME="localhost/exgentic-mcp-${BENCHMARK_NAME}:latest"
TOOL_NAME="exgentic-mcp-${BENCHMARK_NAME}"
NAMESPACE="team1"
KAGENTI_API="http://localhost:8001"  # Using 8001 to avoid conflict with MCP server on 8000
KAGENTI_PORT=8001
KEYCLOAK_API="http://localhost:8002"
KEYCLOAK_PORT=8002

echo "=========================================="
echo "Deploying Exgentic Benchmark: $BENCHMARK_NAME"
echo "=========================================="
echo ""

# Step 1: Check if image exists locally
echo "Step 1: Checking for local image..."
if command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
elif command -v docker &> /dev/null; then
    CONTAINER_CMD="docker"
else
    echo "Error: Neither podman nor docker found"
    exit 1
fi

echo "Using container runtime: $CONTAINER_CMD"

if ! $CONTAINER_CMD image inspect "$IMAGE_NAME" &> /dev/null; then
    echo "Error: Image $IMAGE_NAME not found locally"
    echo "Please build the image first"
    exit 1
fi

echo "✓ Image $IMAGE_NAME found locally"
echo ""

# Step 2: Check if image needs syncing
echo "Step 2: Checking if image sync is needed..."
if ! command -v kind &> /dev/null; then
    echo "Error: kind command not found"
    exit 1
fi

# Get local image ID
LOCAL_IMAGE_ID=$($CONTAINER_CMD inspect "$IMAGE_NAME" --format='{{.Id}}' 2>/dev/null || echo "")

if [ -z "$LOCAL_IMAGE_ID" ]; then
    echo "Error: Could not get local image ID"
    exit 1
fi

echo "Local image ID: $LOCAL_IMAGE_ID"

# Get cluster image ID (check if image exists in cluster)
# Use podman if available, otherwise docker
if command -v podman &> /dev/null; then
    CLUSTER_IMAGE_ID=$(podman exec kagenti-control-plane crictl inspecti "$IMAGE_NAME" 2>/dev/null | grep '"id":' | head -1 | sed 's/.*"id": *"\([^"]*\)".*/\1/' || echo "")
else
    CLUSTER_IMAGE_ID=$(docker exec kagenti-control-plane crictl inspecti "$IMAGE_NAME" 2>/dev/null | grep '"id":' | head -1 | sed 's/.*"id": *"\([^"]*\)".*/\1/' || echo "")
fi

# Normalize IDs by removing sha256: prefix if present
LOCAL_IMAGE_ID_NORMALIZED="${LOCAL_IMAGE_ID#sha256:}"
CLUSTER_IMAGE_ID_NORMALIZED="${CLUSTER_IMAGE_ID#sha256:}"

if [ -z "$CLUSTER_IMAGE_ID" ]; then
    echo "Image not found in cluster, syncing..."
    NEED_SYNC=true
elif [ "$LOCAL_IMAGE_ID_NORMALIZED" != "$CLUSTER_IMAGE_ID_NORMALIZED" ]; then
    echo "Cluster image ID: $CLUSTER_IMAGE_ID"
    echo "Images differ, syncing..."
    NEED_SYNC=true
else
    echo "Cluster image ID: $CLUSTER_IMAGE_ID"
    echo "✓ Images match, skipping sync"
    NEED_SYNC=false
fi

if [ "$NEED_SYNC" = true ]; then
    echo "Saving and loading image..."
    $CONTAINER_CMD save "$IMAGE_NAME" | kind load image-archive /dev/stdin --name kagenti
    echo "✓ Image synced to kind-kagenti cluster"
fi

echo ""

# Step 3: Setting up port-forward to Keycloak...
echo "Step 3: Setting up port-forward to Keycloak..."

# Check if port-forward is already running
if lsof -Pi :$KEYCLOAK_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "✓ Port $KEYCLOAK_PORT is already in use (assuming Keycloak is accessible)"
else
    echo "Starting port-forward to keycloak on port $KEYCLOAK_PORT..."
    kubectl port-forward -n keycloak svc/keycloak-service $KEYCLOAK_PORT:8080 >/dev/null 2>&1 &
    KEYCLOAK_PF_PID=$!
    
    # Wait for port-forward to be ready
    echo "Waiting for Keycloak port-forward to be ready..."
    for i in {1..10}; do
        if curl -s $KEYCLOAK_API/health >/dev/null 2>&1; then
            echo "✓ Keycloak port-forward is ready"
            break
        fi
        if [ $i -eq 10 ]; then
            echo "Warning: Keycloak port-forward may not be ready, continuing anyway..."
        fi
        sleep 1
    done
fi

echo ""

# Step 4: Enable Direct Access Grants for kagenti client if needed
echo "Step 4: Checking Keycloak client configuration..."

# Get admin token first
ADMIN_TOKEN_RESPONSE=$(curl -s -X POST "$KEYCLOAK_API/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=$KEYCLOAK_USERNAME" \
    -d "password=$KEYCLOAK_PASSWORD" \
    -d "grant_type=password" \
    -d "client_id=admin-cli" 2>/dev/null || echo "TOKEN_ERROR")

if [ "$ADMIN_TOKEN_RESPONSE" != "TOKEN_ERROR" ]; then
    ADMIN_TOKEN=$(echo "$ADMIN_TOKEN_RESPONSE" | grep -o '"access_token":"[^"]*"' | sed 's/"access_token":"\([^"]*\)"/\1/')
    
    if [ -n "$ADMIN_TOKEN" ]; then
        # Get kagenti client configuration
        CLIENT_CONFIG=$(curl -s "$KEYCLOAK_API/admin/realms/kagenti/clients?clientId=kagenti" \
            -H "Authorization: Bearer $ADMIN_TOKEN" 2>/dev/null)
        
        CLIENT_ID=$(echo "$CLIENT_CONFIG" | grep -o '"id":"[^"]*"' | head -1 | sed 's/"id":"\([^"]*\)"/\1/')
        
        if [ -n "$CLIENT_ID" ]; then
            # Enable direct access grants
            curl -s -X PUT "$KEYCLOAK_API/admin/realms/kagenti/clients/$CLIENT_ID" \
                -H "Authorization: Bearer $ADMIN_TOKEN" \
                -H "Content-Type: application/json" \
                -d '{"directAccessGrantsEnabled": true}' >/dev/null 2>&1
            echo "✓ Direct access grants enabled for kagenti client"
        fi
    fi
fi

echo ""

# Step 5: Get Keycloak authentication token...
echo "Step 5: Getting Keycloak authentication token..."

# Get token from Keycloak using kagenti client (with direct access grants enabled)
TOKEN_RESPONSE=$(curl -s -X POST "$KEYCLOAK_API/realms/kagenti/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=$KEYCLOAK_USERNAME" \
    -d "password=$KEYCLOAK_PASSWORD" \
    -d "grant_type=password" \
    -d "client_id=kagenti" || echo "TOKEN_ERROR")

if [ "$TOKEN_RESPONSE" = "TOKEN_ERROR" ]; then
    echo "Error: Failed to get authentication token from Keycloak"
    echo "Please check your Keycloak credentials"
    exit 1
fi

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | grep -o '"access_token":"[^"]*"' | sed 's/"access_token":"\([^"]*\)"/\1/')

if [ -z "$ACCESS_TOKEN" ]; then
    echo "Error: Failed to extract access token from Keycloak response"
    echo "Response: $TOKEN_RESPONSE"
    echo ""
    echo "If you see 'unauthorized_client' error, the kagenti client may need Direct Access Grants enabled."
    echo "You can enable it manually in Keycloak admin console or run this script again."
    exit 1
fi

echo "✓ Successfully obtained authentication token"

echo ""

# Step 6: Set up port-forward to Kagenti backend
echo "Step 6: Setting up port-forward to Kagenti backend..."

# Check if port-forward is already running
if lsof -Pi :$KAGENTI_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "✓ Port $KAGENTI_PORT is already in use (assuming Kagenti backend is accessible)"
else
    echo "Starting port-forward to kagenti-backend on port $KAGENTI_PORT..."
    kubectl port-forward -n kagenti-system svc/kagenti-backend $KAGENTI_PORT:8000 >/dev/null 2>&1 &
    PORT_FORWARD_PID=$!
    
    # Wait for port-forward to be ready
    echo "Waiting for port-forward to be ready..."
    for i in {1..10}; do
        if curl -s $KAGENTI_API/api/v1/namespaces >/dev/null 2>&1; then
            echo "✓ Port-forward is ready"
            break
        fi
        if [ $i -eq 10 ]; then
            echo "Error: Port-forward failed to become ready"
            kill $PORT_FORWARD_PID 2>/dev/null || true
            exit 1
        fi
        sleep 1
    done
fi

echo ""

# Step 7: Delete existing tool via Kagenti API if it exists
echo "Step 7: Deleting existing tool via Kagenti API if it exists..."
DELETE_RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/kagenti_delete_response.txt -X DELETE "$KAGENTI_API/api/v1/tools/$NAMESPACE/$TOOL_NAME" \
    -H "Authorization: Bearer $ACCESS_TOKEN")

if [ "$DELETE_RESPONSE" = "200" ] || [ "$DELETE_RESPONSE" = "404" ]; then
    echo "✓ Tool deleted or did not exist (HTTP $DELETE_RESPONSE)"
else
    echo "Warning: Delete returned HTTP $DELETE_RESPONSE"
    cat /tmp/kagenti_delete_response.txt
fi

# Wait a moment for deletion to complete
sleep 3

echo ""

# Step 8: Fetch and parse benchmark environment variables
echo "Step 8: Fetching benchmark environment variables..."
ENV_CONTENT=$(curl -s "https://raw.githubusercontent.com/yoavkatz/agent-examples/refs/heads/feature/exgentic-mcp-server/mcp/exgentic_benchmarks/.env.${BENCHMARK_NAME}")

if [ -z "$ENV_CONTENT" ] || echo "$ENV_CONTENT" | grep -q "404: Not Found"; then
    echo "Warning: Could not fetch .env.${BENCHMARK_NAME} file, deploying without custom env vars"
    ENV_VARS="[]"
else
    # Parse env vars using the Kagenti API
    ENV_PARSE_RESPONSE=$(curl -s -X POST "$KAGENTI_API/api/v1/agents/parse-env" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -d "{\"content\": $(echo "$ENV_CONTENT" | jq -Rs .)}")
    
    ENV_VARS=$(echo "$ENV_PARSE_RESPONSE" | jq '.envVars')
    
    if [ "$ENV_VARS" = "null" ] || [ -z "$ENV_VARS" ]; then
        echo "Warning: Could not parse environment variables, deploying without custom env vars"
        ENV_VARS="[]"
    else
        echo "✓ Environment variables parsed"
    fi
fi

echo ""

# Step 9: Deploy tool using Kagenti API
echo "Step 9: Deploying tool via Kagenti API..."

# Create tool deployment JSON following Kagenti API format
TOOL_JSON=$(cat <<EOF
{
  "name": "$TOOL_NAME",
  "namespace": "$NAMESPACE",
  "protocol": "mcp",
  "framework": "custom",
  "deploymentMethod": "image",
  "containerImage": "$IMAGE_NAME",
  "workloadType": "deployment",
  "envVars": $ENV_VARS,
  "servicePorts": [
    {
      "name": "http",
      "port": 8000,
      "targetPort": 8000,
      "protocol": "TCP"
    }
  ],
  "createHttpRoute": false,
  "authBridgeEnabled": false,
  "spireEnabled": false
}
EOF
)

echo "Tool configuration:"
echo "$TOOL_JSON"
echo ""

# Deploy tool using official Kagenti API with authentication
HTTP_CODE=$(curl -s -w "%{http_code}" -o /tmp/kagenti_response.txt -X POST "$KAGENTI_API/api/v1/tools" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -d "$TOOL_JSON")

RESPONSE=$(cat /tmp/kagenti_response.txt)

echo "API Response (HTTP $HTTP_CODE):"
echo "$RESPONSE"
echo ""

# Check if deployment was successful
if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    echo "✓ Tool deployment successful"
elif [ "$HTTP_CODE" = "409" ]; then
    echo "✓ Tool already exists (HTTP 409)"
else
    echo "Error: Kagenti API deployment failed with HTTP $HTTP_CODE"
    echo "Response: $RESPONSE"
    echo ""
    echo "Please ensure:"
    echo "  1. Kagenti API is running at $KAGENTI_API"
    echo "  2. The API endpoint is correct"
    echo "  3. You have proper permissions"
    exit 1
fi
echo ""

# Step 10: Patch imagePullPolicy to IfNotPresent for local images
echo "Step 10: Patching imagePullPolicy to IfNotPresent..."
sleep 2  # Give the deployment a moment to be created
kubectl patch deployment $TOOL_NAME -n $NAMESPACE -p '{"spec":{"template":{"spec":{"containers":[{"name":"mcp","imagePullPolicy":"IfNotPresent"}]}}}}' 2>/dev/null || echo "Warning: Could not patch imagePullPolicy"
echo "✓ ImagePullPolicy patched"

echo ""

# Step 11: Wait for tool to be ready
echo "Step 11: Waiting for tool to be ready..."

MAX_WAIT=120
WAIT_INTERVAL=5
ELAPSED=0

while [ $ELAPSED -lt $MAX_WAIT ]; do
    # Check if pod is running (using Kagenti's label format)
    POD_STATUS=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=$TOOL_NAME -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "NotFound")
    
    if [ "$POD_STATUS" = "Running" ]; then
        # Check if pod is ready
        POD_READY=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=$TOOL_NAME -o jsonpath='{.items[0].status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")
        
        if [ "$POD_READY" = "True" ]; then
            echo "✓ Tool is ready!"
            
            # Get pod name
            POD_NAME=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=$TOOL_NAME -o jsonpath='{.items[0].metadata.name}')
            echo ""
            echo "Pod: $POD_NAME"
            echo "Service: $TOOL_NAME.$NAMESPACE:8000"
            echo ""
            echo "To access the tool:"
            echo "  kubectl port-forward -n $NAMESPACE svc/$TOOL_NAME 8000:8000"
            echo ""
            exit 0
        fi
    fi
    
    echo "  Status: $POD_STATUS (waiting...)"
    sleep $WAIT_INTERVAL
    ELAPSED=$((ELAPSED + WAIT_INTERVAL))
done

echo "Error: Tool did not become ready within ${MAX_WAIT}s"
echo ""
echo "Check status with:"
echo "  kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=$TOOL_NAME"
echo "  kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=$TOOL_NAME"
exit 1

# Made with Bob
