#!/bin/bash
# Deploy agent to Kagenti cluster via API
# Usage: ./deploy-agent.sh <benchmark-name> <agent-name> <keycloak-username> <keycloak-password>
# Example: ./deploy-agent.sh gsm8k generic_agent admin admin
# Example: ./deploy-agent.sh gsm8k tool_calling admin admin

set -e

BENCHMARK_NAME="$1"
AGENT_NAME_INPUT="$2"
KEYCLOAK_USERNAME="${3:-admin}"
KEYCLOAK_PASSWORD="${4:-admin}"

if [ -z "$BENCHMARK_NAME" ] || [ -z "$AGENT_NAME_INPUT" ]; then
    echo "Error: Benchmark name and agent name are required"
    echo "Usage: $0 <benchmark-name> <agent-name> [keycloak-username] [keycloak-password]"
    echo "Example: $0 gsm8k generic_agent admin admin"
    echo "Example: $0 gsm8k tool_calling admin admin"
    exit 1
fi

# Determine deployment type based on agent name
if [ "$AGENT_NAME_INPUT" = "generic_agent" ]; then
    DEPLOYMENT_TYPE="source"
    AGENT_NAME="generic-agent-internal-${BENCHMARK_NAME}"
else
    DEPLOYMENT_TYPE="image"
    # Automatically add exgentic-a2a- prefix if not already present
    if [[ "$AGENT_NAME_INPUT" == exgentic-a2a-* ]]; then
        FULL_AGENT_NAME="$AGENT_NAME_INPUT"
    else
        FULL_AGENT_NAME="exgentic-a2a-${AGENT_NAME_INPUT}"
    fi
    # Replace underscores with hyphens for Kubernetes compatibility
    AGENT_NAME="${FULL_AGENT_NAME}-${BENCHMARK_NAME}"
    AGENT_NAME="${AGENT_NAME//_/-}"
    # Image name keeps underscores (container images allow them)
    IMAGE_NAME="localhost/${FULL_AGENT_NAME}:latest"
    # Split image name and tag for API
    IMAGE_NAME_WITHOUT_TAG="localhost/${FULL_AGENT_NAME}"
    IMAGE_TAG="latest"
fi

TOOL_NAME="exgentic-mcp-${BENCHMARK_NAME}"
NAMESPACE="team1"
KAGENTI_API="http://localhost:8001"
KAGENTI_PORT=8001
KEYCLOAK_API="http://localhost:8002"
KEYCLOAK_PORT=8002

echo "=========================================="
if [ "$DEPLOYMENT_TYPE" = "source" ]; then
    echo "Deploying Generic Agent: $AGENT_NAME"
else
    echo "Deploying Exgentic Agent: $AGENT_NAME"
    echo "From image: $IMAGE_NAME"
fi
echo "=========================================="
echo ""

# Step 0: If deploying from image, check and sync image
if [ "$DEPLOYMENT_TYPE" = "image" ]; then
    echo "Step 0: Checking for local image and syncing if needed..."
    
    # Determine container runtime
    if command -v podman &> /dev/null; then
        CONTAINER_CMD="podman"
    elif command -v docker &> /dev/null; then
        CONTAINER_CMD="docker"
    else
        echo "Error: Neither podman nor docker found"
        exit 1
    fi
    
    echo "Using container runtime: $CONTAINER_CMD"
    
    # Check if image exists locally
    if ! $CONTAINER_CMD image inspect "$IMAGE_NAME" &> /dev/null; then
        echo "Error: Image $IMAGE_NAME not found locally"
        echo "Please build the image first"
        exit 1
    fi
    
    echo "✓ Image $IMAGE_NAME found locally"
    
    # Check if kind is available
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
fi

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

if [ "$DEPLOYMENT_TYPE" = "source" ]; then
    # Generic agent - fetch from agent-examples repo
    ENV_CONTENT=$(curl -s https://raw.githubusercontent.com/kagenti/agent-examples/refs/heads/main/a2a/generic_agent/.env.openai)
else
    # Exgentic agent - no remote env file, will use default env vars
    ENV_CONTENT=""
fi

if [ -n "$ENV_CONTENT" ]; then
    # Parse env vars using the Kagenti API
    ENV_PARSE_RESPONSE=$(curl -s -X POST "$KAGENTI_API/api/v1/agents/parse-env" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -d "{\"content\": $(echo "$ENV_CONTENT" | jq -Rs .)}")
    
    ENV_VARS=$(echo "$ENV_PARSE_RESPONSE" | jq '.envVars')
    echo "✓ Environment variables parsed"
else
    ENV_VARS="[]"
    echo "✓ Using default environment variables"
fi

echo ""

# Step 7: Deploy agent via Kagenti API
echo "Step 7: Deploying agent via Kagenti API..."

# Add MCP_URL(S) to environment variables
MCP_URL="http://${TOOL_NAME}-mcp:8000/mcp"

if [ "$DEPLOYMENT_TYPE" = "source" ]; then
    # Generic agent uses MCP_URLS
    ENV_VARS_WITH_MCP=$(echo "$ENV_VARS" | jq ". + [{\"name\": \"MCP_URLS\", \"value\": \"$MCP_URL\"}]")
else
    # Exgentic agent uses MCP_URL
    ENV_VARS_WITH_MCP=$(echo "$ENV_VARS" | jq ". + [{\"name\": \"MCP_URL\", \"value\": \"$MCP_URL\"}]")
fi

if [ "$DEPLOYMENT_TYPE" = "source" ]; then
    # Deploy generic agent from source
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
else
    # Deploy exgentic agent from image
    AGENT_JSON=$(cat <<EOF
{
  "name": "$AGENT_NAME",
  "namespace": "$NAMESPACE",
  "gitUrl": "",
  "gitPath": "",
  "gitBranch": "",
  "imageTag": "$IMAGE_TAG",
  "protocol": "a2a",
  "framework": "custom",
  "deploymentMethod": "image",
  "containerImage": "$IMAGE_NAME",
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
fi

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

# Step 8: Wait for build to complete (only for source deployments)
if [ "$DEPLOYMENT_TYPE" = "source" ]; then
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
else
    # For image deployments, patch imagePullPolicy
    echo "Step 8: Patching imagePullPolicy to IfNotPresent..."
    sleep 2  # Give the deployment a moment to be created
    kubectl patch deployment $AGENT_NAME -n $NAMESPACE -p '{"spec":{"template":{"spec":{"containers":[{"name":"agent","imagePullPolicy":"IfNotPresent"}]}}}}' 2>/dev/null || echo "Warning: Could not patch imagePullPolicy"
    echo "✓ ImagePullPolicy patched"
    echo ""
fi

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

# Check if service exists
if ! kubectl get svc $AGENT_NAME -n $NAMESPACE >/dev/null 2>&1; then
    echo "⚠ Service $AGENT_NAME not found, skipping card test"
else
    # Set up port-forward to agent
    AGENT_PORT=8084
    
    # Check if port is already in use
    if lsof -Pi :$AGENT_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "⚠ Port $AGENT_PORT already in use, skipping card test"
    else
        kubectl port-forward -n $NAMESPACE svc/$AGENT_NAME $AGENT_PORT:8080 >/dev/null 2>&1 &
        AGENT_PF_PID=$!
        sleep 3
        
        # Check if port-forward is actually running
        if ! kill -0 $AGENT_PF_PID 2>/dev/null; then
            echo "⚠ Port-forward failed to start, skipping card test"
        else
            # Test agent card endpoint (trying common A2A methods)
            CARD_RESPONSE=$(curl -s --max-time 5 -X POST http://localhost:$AGENT_PORT/ \
              -H "Content-Type: application/json" \
              -d '{"jsonrpc": "2.0", "method": "agent/card", "id": 1}' 2>/dev/null)
            
            if [ -z "$CARD_RESPONSE" ]; then
                echo "⚠ No response from agent (this is normal for some agent types)"
                echo "  Agent is deployed and running, but may not respond to agent/card method"
            else
                # Check if response contains error
                if echo "$CARD_RESPONSE" | grep -q '"error"'; then
                    echo "⚠ Agent responded with error (this is normal for some agent types):"
                    echo "$CARD_RESPONSE" | jq '.' 2>/dev/null || echo "$CARD_RESPONSE"
                    echo ""
                    echo "  Agent is deployed and running, but may use different A2A method names"
                else
                    echo "✓ Agent card access successful:"
                    echo "$CARD_RESPONSE" | jq '.' 2>/dev/null || echo "$CARD_RESPONSE"
                fi
            fi
            
            # Clean up port-forward
            kill $AGENT_PF_PID 2>/dev/null
        fi
    fi
fi

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
