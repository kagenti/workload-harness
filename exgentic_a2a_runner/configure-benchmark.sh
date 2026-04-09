#!/bin/bash
# Configure benchmark environment settings
# Usage: ./configure-benchmark.sh <benchmark-name> [model-name]
# Example: ./configure-benchmark.sh gsm8k
# Example: ./configure-benchmark.sh tau2 Azure/gpt-4o-mini
# This script updates the Kubernetes secret and environment variables for the benchmark

set -e

BENCHMARK_NAME="$1"
MODEL_NAME="${2:-Azure/gpt-4o}"  # Default to Azure/gpt-4o if not provided

if [ -z "$BENCHMARK_NAME" ]; then
    echo "Error: Benchmark name is required"
    echo "Usage: $0 <benchmark-name> [model-name]"
    echo "Example: $0 gsm8k"
    echo "Example: $0 tau2 Azure/gpt-4o-mini"
    exit 1
fi

NAMESPACE="team1"
BENCHMARK_DEPLOYMENT="exgentic-mcp-${BENCHMARK_NAME}"

echo "=========================================="
echo "Configuring Benchmark Environment"
echo "=========================================="
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

# Step 2: Update benchmark deployment with Azure OpenAI settings
echo "Step 2: Updating benchmark deployment with Azure OpenAI settings..."

if [ -z "$OPENAI_API_BASE" ]; then
    echo "Error: OPENAI_API_BASE environment variable is not set"
    exit 1
fi

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
    
    # Step 3: Wait for benchmark rollout
    echo "Step 3: Waiting for benchmark deployment rollout..."
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
    echo "✗ Benchmark deployment not found: $BENCHMARK_DEPLOYMENT"
    exit 1
fi

echo ""
echo "=========================================="
echo "Benchmark Configuration Complete!"
echo "=========================================="
echo ""

# Made with Bob