#!/bin/bash
# Configure agent environment settings
# Usage: ./configure-agent.sh <benchmark-name> <agent-name> [model-name]
# Example: ./configure-agent.sh tau2 tool_calling
# Example: ./configure-agent.sh tau2 tool_calling Azure/gpt-4o-mini
# This script updates the Kubernetes secret and environment variables for the agent

set -e

BENCHMARK_NAME="$1"
AGENT_NAME_INPUT="$2"
MODEL_NAME="${3:-Azure/gpt-4o}"  # Default to Azure/gpt-4o if not provided

if [ -z "$BENCHMARK_NAME" ] || [ -z "$AGENT_NAME_INPUT" ]; then
    echo "Error: Benchmark name and agent name are required"
    echo "Usage: $0 <benchmark-name> <agent-name> [model-name]"
    echo "Example: $0 tau2 tool_calling"
    echo "Example: $0 tau2 tool_calling Azure/gpt-4o-mini"
    exit 1
fi

NAMESPACE="team1"

# Construct agent deployment name
if [[ "$AGENT_NAME_INPUT" == exgentic-a2a-* ]]; then
    FULL_AGENT_NAME="$AGENT_NAME_INPUT"
else
    FULL_AGENT_NAME="exgentic-a2a-${AGENT_NAME_INPUT}"
fi
# Replace underscores with hyphens for Kubernetes compatibility
AGENT_NAME="${FULL_AGENT_NAME}-${BENCHMARK_NAME}"
AGENT_NAME="${AGENT_NAME//_/-}"

echo "=========================================="
echo "Configuring Agent Environment"
echo "=========================================="
echo "Agent: $AGENT_NAME"
echo "Model: $MODEL_NAME"
echo ""

# Step 1: Update the openai-secret with current OPENAI_API_KEY
echo "Step 1: Updating openai-secret with OPENAI_API_KEY..."

if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY environment variable is not set"
    exit 1
fi

# Encode the API key in base64
ENCODED_KEY=$(echo -n "$OPENAI_API_KEY" | base64)

# Patch the secret
kubectl patch secret openai-secret -n $NAMESPACE --type='json' -p="[
  {
    \"op\": \"replace\",
    \"path\": \"/data/apikey\",
    \"value\": \"$ENCODED_KEY\"
  }
]"

echo "✓ Secret updated"
echo ""

# Step 2: Update agent deployment with Azure OpenAI settings
echo "Step 2: Updating agent deployment with Azure OpenAI settings..."

if [ -z "$OPENAI_API_BASE" ]; then
    echo "Error: OPENAI_API_BASE environment variable is not set"
    exit 1
fi

# Check if agent deployment exists
if kubectl get deployment $AGENT_NAME -n $NAMESPACE >/dev/null 2>&1; then
    # Use kubectl set env to update environment variables
    kubectl set env deployment/$AGENT_NAME -n $NAMESPACE \
        LLM_API_BASE="$OPENAI_API_BASE" \
        OPENAI_API_BASE="$OPENAI_API_BASE" \
        LLM_MODEL="$MODEL_NAME" \
        EXGENTIC_SET_AGENT_MODEL="$MODEL_NAME"

    echo "✓ Agent environment variables updated"
    echo ""

    # Step 3: Wait for agent rollout
    echo "Step 3: Waiting for agent deployment rollout..."
    kubectl rollout status deployment/$AGENT_NAME -n $NAMESPACE --timeout=120s

    echo "✓ Agent rollout complete"
    echo ""

    echo "Agent configuration applied:"
    echo "  Deployment: $AGENT_NAME"
    echo "  LLM_API_BASE: $OPENAI_API_BASE"
    echo "  OPENAI_API_BASE: $OPENAI_API_BASE"
    echo "  LLM_MODEL: $MODEL_NAME"
    echo "  EXGENTIC_SET_AGENT_MODEL=$MODEL_NAME"
    echo "  OPENAI_API_KEY: (updated secret from env var)"
else
    echo "✗ Agent deployment not found: $AGENT_NAME"
    exit 1
fi

echo ""
echo "=========================================="
echo "Agent Configuration Complete!"
echo "=========================================="
echo ""

# Made with Bob