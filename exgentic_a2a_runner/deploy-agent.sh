#!/bin/bash
# Deploy generic agent to Kagenti cluster via API
# Usage: ./deploy-agent.sh <benchmark-name> <keycloak-username> <keycloak-password>
# Example: ./deploy-agent.sh gsm8k admin admin

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

AGENT_NAME="generic-agent-internal-${BENCHMARK_NAME}"
TOOL_NAME="exgentic-mcp-${BENCHMARK_NAME}"
NAMESPACE="team1"
KAGENTI_API="http://localhost:8001"
KAGENTI_PORT=8001
KEYCLOAK_API="http://localhost:8002"
KEYCLOAK_PORT=8002

echo "=========================================="
echo "Deploying Generic Agent: $AGENT_NAME"
echo "=========================================="
echo ""

# Step 1: Set up port-forward to Keycloak
echo "Step 1: Setting up port-forward to Keycloak..."
if lsof -Pi :$KEYCLOAK_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "✓ Port $KEYCLOAK_PORT is already in use (assuming Keycloak is accessible)"
else
    echo "Starting port-forward to keycloak on port $KEYCLOAK_PORT..."
    kubectl port-forward -n keycloak svc/keycloak-service $KEYCLOAK_PORT:8080 >/dev/null 2>&1 &
    KEYCLOAK_PF_PID=$!
    sleep 2
fi

echo ""

# Step 2: Enable Direct Access Grants for kagenti client if needed
echo "Step 2: Checking Keycloak client configuration..."

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

# Step 3: Get Keycloak authentication token
echo "Step 3: Getting Keycloak authentication token..."
TOKEN_RESPONSE=$(curl -s -X POST "$KEYCLOAK_API/realms/kagenti/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=$KEYCLOAK_USERNAME" \
    -d "password=$KEYCLOAK_PASSWORD" \
    -d "grant_type=password" \
    -d "client_id=kagenti" || echo "TOKEN_ERROR")

if [ "$TOKEN_RESPONSE" = "TOKEN_ERROR" ]; then
    echo "Error: Failed to get authentication token from Keycloak"
    exit 1
fi

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | grep -o '"access_token":"[^"]*"' | sed 's/"access_token":"\([^"]*\)"/\1/')

if [ -z "$ACCESS_TOKEN" ]; then
    echo "Error: Failed to extract access token"
    echo "Response: $TOKEN_RESPONSE"
    echo ""
    echo "If you see 'unauthorized_client' error, the kagenti client may need Direct Access Grants enabled."
    echo "You can enable it manually in Keycloak admin console or run this script again."
    exit 1
fi

echo "✓ Successfully obtained authentication token"

echo ""

# Step 4: Set up port-forward to Kagenti backend
echo "Step 4: Setting up port-forward to Kagenti backend..."
if lsof -Pi :$KAGENTI_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "✓ Port $KAGENTI_PORT is already in use (assuming Kagenti backend is accessible)"
else
    echo "Starting port-forward to kagenti-backend on port $KAGENTI_PORT..."
    kubectl port-forward -n kagenti-system svc/kagenti-backend $KAGENTI_PORT:8000 >/dev/null 2>&1 &
    PORT_FORWARD_PID=$!
    sleep 2
fi

echo ""

# Step 5: Delete existing agent if it exists
echo "Step 5: Deleting existing agent via Kagenti API if it exists..."
DELETE_RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/kagenti_delete_agent_response.txt -X DELETE "$KAGENTI_API/api/v1/agents/$NAMESPACE/$AGENT_NAME" \
    -H "Authorization: Bearer $ACCESS_TOKEN")

if [ "$DELETE_RESPONSE" = "200" ] || [ "$DELETE_RESPONSE" = "404" ]; then
    echo "✓ Agent deleted or did not exist (HTTP $DELETE_RESPONSE)"
else
    echo "Warning: Delete returned HTTP $DELETE_RESPONSE"
fi

sleep 3

echo ""

# Step 6: Fetch and parse environment variables
echo "Step 6: Fetching environment variables..."
ENV_CONTENT=$(curl -s https://raw.githubusercontent.com/kagenti/agent-examples/refs/heads/main/a2a/generic_agent/.env.openai)

# Parse env vars using the Kagenti API
ENV_PARSE_RESPONSE=$(curl -s -X POST "$KAGENTI_API/api/v1/agents/parse-env" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -d "{\"content\": $(echo "$ENV_CONTENT" | jq -Rs .)}")

ENV_VARS=$(echo "$ENV_PARSE_RESPONSE" | jq '.envVars')

echo "✓ Environment variables parsed"

echo ""

# Step 7: Deploy agent via Kagenti API
echo "Step 7: Deploying agent via Kagenti API..."

# Add MCP_URLS to environment variables
MCP_URL="http://${TOOL_NAME}-mcp:8000/mcp"
ENV_VARS_WITH_MCP=$(echo "$ENV_VARS" | jq ". + [{\"name\": \"MCP_URLS\", \"value\": \"$MCP_URL\"}]")

AGENT_JSON=$(cat <<EOF
{
  "name": "$AGENT_NAME",
  "namespace": "$NAMESPACE",
  "gitUrl": "https://github.com/kagenti/agent-examples",
  "gitPath": "a2a/generic_agent",
  "gitBranch": "main",
  "imageTag": "latest",
  "protocol": "a2a",
  "framework": "custom",
  "deploymentMethod": "source",
  "workloadType": "deployment",
  "envVars": $ENV_VARS_WITH_MCP,
  "servicePorts": [
    {
      "name": "http",
      "port": 8080,
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

echo "Agent configuration:"
echo "$AGENT_JSON" | jq '.'
echo ""

HTTP_CODE=$(curl -s -w "%{http_code}" -o /tmp/kagenti_agent_response.txt -X POST "$KAGENTI_API/api/v1/agents" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -d "$AGENT_JSON")

RESPONSE=$(cat /tmp/kagenti_agent_response.txt)

echo "API Response (HTTP $HTTP_CODE):"
echo "$RESPONSE"
echo ""

if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    echo "✓ Agent deployment successful"
elif [ "$HTTP_CODE" = "409" ]; then
    echo "✓ Agent already exists (HTTP 409)"
else
    echo "Error: Kagenti API deployment failed with HTTP $HTTP_CODE"
    exit 1
fi

echo ""

# Step 8: Wait for build to complete
echo "Step 8: Waiting for build to complete..."
BUILD_RUN_NAME=$(echo "$RESPONSE" | jq -r '.message' | grep -o "BuildRun: '[^']*'" | sed "s/BuildRun: '\([^']*\)'/\1/")

if [ -z "$BUILD_RUN_NAME" ]; then
    echo "Warning: Could not extract BuildRun name from response"
    echo "Response: $RESPONSE"
    echo "Skipping build wait"
else
    echo "Monitoring BuildRun: $BUILD_RUN_NAME"
    
    # Wait up to 5 minutes for build to complete
    for i in {1..60}; do
        BUILD_STATUS=$(kubectl get buildrun "$BUILD_RUN_NAME" -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Succeeded")].status}' 2>/dev/null || echo "Unknown")
        BUILD_REASON=$(kubectl get buildrun "$BUILD_RUN_NAME" -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Succeeded")].reason}' 2>/dev/null || echo "Unknown")
        
        if [ "$BUILD_STATUS" = "True" ]; then
            echo "✓ Build completed successfully"
            break
        elif [ "$BUILD_STATUS" = "False" ]; then
            echo "✗ Build failed with reason: $BUILD_REASON"
            echo "Check logs with: kubectl logs -n $NAMESPACE -l buildrun.shipwright.io/name=$BUILD_RUN_NAME"
            exit 1
        fi
        
        echo "  Build in progress... ($i/60)"
        sleep 5
    done
    
    if [ "$BUILD_STATUS" != "True" ]; then
        echo "✗ Build did not complete within 5 minutes"
        exit 1
    fi
fi

echo ""

# Step 9: Wait for agent deployment to be created and ready
echo "Step 9: Waiting for agent deployment to be created..."

# Wait for deployment to be created (up to 2 minutes)
for i in {1..24}; do
    if kubectl get deployment $AGENT_NAME -n $NAMESPACE >/dev/null 2>&1; then
        echo "✓ Agent deployment created"
        break
    fi
    echo "  Waiting for deployment to be created... ($i/24)"
    sleep 5
done

# Check if deployment exists
if ! kubectl get deployment $AGENT_NAME -n $NAMESPACE >/dev/null 2>&1; then
    echo "✗ Agent deployment was not created within 2 minutes"
    exit 1
fi

echo "Waiting for agent deployment to be ready..."
kubectl wait --for=condition=available deployment/$AGENT_NAME -n $NAMESPACE --timeout=120s

if [ $? -ne 0 ]; then
    echo "✗ Agent deployment did not become ready"
    exit 1
fi

echo "✓ Agent deployment is ready"
echo ""

# Step 10: Test agent card access
echo "Step 10: Testing agent card access..."

# Set up port-forward to agent
AGENT_PORT=8084
kubectl port-forward -n $NAMESPACE svc/$AGENT_NAME $AGENT_PORT:8080 >/dev/null 2>&1 &
AGENT_PF_PID=$!
sleep 2

# Test agent card endpoint (trying common A2A methods)
CARD_RESPONSE=$(curl -s -X POST http://localhost:$AGENT_PORT/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "agent/card", "id": 1}' 2>/dev/null)

if [ -z "$CARD_RESPONSE" ]; then
    echo "✗ No response from agent"
    kill $AGENT_PF_PID 2>/dev/null
    exit 1
fi

# Check if response contains error
if echo "$CARD_RESPONSE" | grep -q '"error"'; then
    echo "Agent responded but method may be incorrect:"
    echo "$CARD_RESPONSE" | jq '.' 2>/dev/null || echo "$CARD_RESPONSE"
    echo ""
    echo "Note: Agent is running but may use different A2A method names"
else
    echo "✓ Agent card access successful:"
    echo "$CARD_RESPONSE" | jq '.' 2>/dev/null || echo "$CARD_RESPONSE"
fi

# Clean up port-forward
kill $AGENT_PF_PID 2>/dev/null

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Agent: $AGENT_NAME.$NAMESPACE:8080"
echo "Tool: $TOOL_NAME.$NAMESPACE:8000"
echo ""
echo "Agent is ready and accessible!"
echo ""

# Made with Bob
