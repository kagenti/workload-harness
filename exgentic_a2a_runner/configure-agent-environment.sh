#!/bin/bash
# Configure agent environment settings
# Usage: ./configure-agent-environment.sh <benchmark-name>
# Example: ./configure-agent-environment.sh gsm8k
# This script updates the Kubernetes secret and patches the agent deployment

set -e

BENCHMARK_NAME="$1"

if [ -z "$BENCHMARK_NAME" ]; then
    echo "Error: Benchmark name is required"
    echo "Usage: $0 <benchmark-name>"
    echo "Example: $0 gsm8k"
    exit 1
fi

NAMESPACE="team1"
AGENT_NAME="generic-agent-internal-${BENCHMARK_NAME}"

echo "=========================================="
echo "Configuring Agent Environment: $AGENT_NAME"
echo "=========================================="
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

# Step 2: Patch agent deployment with Azure OpenAI settings
echo "Step 2: Patching agent deployment with Azure OpenAI settings..."

if [ -z "$OPENAI_API_BASE" ]; then
    echo "Error: OPENAI_API_BASE environment variable is not set"
    exit 1
fi

# Get current env vars
CURRENT_ENV=$(kubectl get deployment $AGENT_NAME -n $NAMESPACE -o json | jq '.spec.template.spec.containers[0].env')

# Find indices of the env vars we need to update
LLM_API_BASE_INDEX=$(echo "$CURRENT_ENV" | jq 'map(.name == "LLM_API_BASE") | index(true)')
LLM_MODEL_INDEX=$(echo "$CURRENT_ENV" | jq 'map(.name == "LLM_MODEL") | index(true)')

if [ "$LLM_API_BASE_INDEX" = "null" ] || [ "$LLM_MODEL_INDEX" = "null" ]; then
    echo "Error: Could not find LLM_API_BASE or LLM_MODEL in deployment"
    exit 1
fi

# Patch only the specific env vars
kubectl patch deployment $AGENT_NAME -n $NAMESPACE --type='json' -p="[
  {
    \"op\": \"replace\",
    \"path\": \"/spec/template/spec/containers/0/env/$LLM_API_BASE_INDEX/value\",
    \"value\": \"$OPENAI_API_BASE\"
  },
  {
    \"op\": \"replace\",
    \"path\": \"/spec/template/spec/containers/0/env/$LLM_MODEL_INDEX/value\",
    \"value\": \"Azure/gpt-4o\"
  }
]"

echo "✓ Deployment patched"
echo ""

# Step 3: Wait for rollout
echo "Step 3: Waiting for deployment rollout..."
kubectl rollout status deployment/$AGENT_NAME -n $NAMESPACE --timeout=120s

echo "✓ Rollout complete"
echo ""

echo "=========================================="
echo "Configuration Complete!"
echo "=========================================="
echo ""
echo "Settings applied:"
echo "  LLM_API_BASE: $OPENAI_API_BASE"
echo "  LLM_MODEL: Azure/gpt-4o"
echo "  OPENAI_API_KEY: (from secret)"
echo ""

# Made with Bob
