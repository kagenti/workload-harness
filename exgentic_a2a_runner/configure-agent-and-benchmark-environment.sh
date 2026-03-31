#!/bin/bash
# Configure agent and benchmark environment settings
# Usage: ./configure-agent-environment.sh <benchmark-name> [model-name]
# Example: ./configure-agent-environment.sh gsm8k
# Example: ./configure-agent-environment.sh gsm8k Azure/gpt-4o-mini
# This script updates the Kubernetes secret and environment variables for both agent and benchmark

set -e

BENCHMARK_NAME="$1"
MODEL_NAME="${2:-Azure/gpt-4o}"  # Default to Azure/gpt-4o if not provided

if [ -z "$BENCHMARK_NAME" ]; then
    echo "Error: Benchmark name is required"
    echo "Usage: $0 <benchmark-name> [model-name]"
    echo "Example: $0 gsm8k"
    echo "Example: $0 gsm8k Azure/gpt-4o-mini"
    exit 1
fi

NAMESPACE="team1"
AGENT_NAME="generic-agent-internal-${BENCHMARK_NAME}"
BENCHMARK_DEPLOYMENT="exgentic-mcp-${BENCHMARK_NAME}"

echo "=========================================="
echo "Configuring Environment"
echo "=========================================="
echo "Agent: $AGENT_NAME"
echo "Benchmark: $BENCHMARK_DEPLOYMENT"
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

echo "=========================================="
echo "AGENT CONFIGURATION"
echo "=========================================="
echo ""

# Step 2: Update agent deployment with Azure OpenAI settings
echo "Step 2: Updating agent deployment with Azure OpenAI settings..."

if [ -z "$OPENAI_API_BASE" ]; then
    echo "Error: OPENAI_API_BASE environment variable is not set"
    exit 1
fi

# Use kubectl set env to update environment variables
kubectl set env deployment/$AGENT_NAME -n $NAMESPACE \
    LLM_API_BASE="$OPENAI_API_BASE" \
    OPENAI_API_BASE="$OPENAI_API_BASE" \
    LLM_MODEL="$MODEL_NAME"

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
echo "  OPENAI_API_KEY: (updated secret from env var)"
echo ""

echo "=========================================="
echo "BENCHMARK CONFIGURATION"
echo "=========================================="
echo ""

# Step 4: Update benchmark deployment with Azure OpenAI settings
echo "Step 4: Updating benchmark deployment with Azure OpenAI settings..."

# Check if benchmark deployment exists
if kubectl get deployment $BENCHMARK_DEPLOYMENT -n $NAMESPACE >/dev/null 2>&1; then
    # Set memory limit to 3GB
    kubectl set resources deployment/$BENCHMARK_DEPLOYMENT -n $NAMESPACE \
        --limits=memory=3Gi
    
    echo "✓ Benchmark memory limit set to 3Gi"
    echo ""
    
    # Set OPENAI_API_BASE for all benchmarks
    kubectl set env deployment/$BENCHMARK_DEPLOYMENT -n $NAMESPACE \
        OPENAI_API_BASE="$OPENAI_API_BASE"
    
    # Only set EXGENTIC_SET_BENCHMARK_USER_SIMULATOR_MODEL for tau benchmarks
    if [[ "$BENCHMARK_NAME" == tau* ]]; then
        kubectl set env deployment/$BENCHMARK_DEPLOYMENT -n $NAMESPACE \
            EXGENTIC_SET_BENCHMARK_USER_SIMULATOR_MODEL="openai/$MODEL_NAME"
        echo "✓ Benchmark environment variables updated (including user simulator model for tau benchmark)"
    else
        echo "✓ Benchmark environment variables updated"
    fi
    
    echo ""
    
    # Step 5: Wait for benchmark rollout
    echo "Step 5: Waiting for benchmark deployment rollout..."
    kubectl rollout status deployment/$BENCHMARK_DEPLOYMENT -n $NAMESPACE --timeout=120s
    echo "✓ Benchmark rollout complete"
    echo ""
    
    echo "Benchmark configuration applied:"
    echo "  Deployment: $BENCHMARK_DEPLOYMENT"
    echo "  Memory Limit: 3Gi"
    echo "  OPENAI_API_BASE: $OPENAI_API_BASE"
    if [[ "$BENCHMARK_NAME" == tau* ]]; then
        echo "  EXGENTIC_SET_BENCHMARK_USER_SIMULATOR_MODEL: openai/$MODEL_NAME"
    fi
    echo "  OPENAI_API_KEY: (updated secret from env var)"
else
    echo "⚠ Benchmark deployment not found, skipping"
fi

echo ""

echo "=========================================="
echo "Configuration Complete!"
echo "=========================================="
echo ""

# Made with Bob
