#!/usr/bin/env bash
#
# Run a benchmark twice for comparison: once with a plugin preset and once
# without any plugins (baseline). Experiment names are derived from the
# parameters.
#
# Usage:
#   ./run-ibac-comparison.sh [OPTIONS]
#
# Options:
#   --model MODEL                  Model name (default: gcp/gemini-3-flash-preview)
#   --benchmark NAME               Benchmark name (default: gsm8k)
#   --agent NAME                   Agent name (default: tool_calling)
#   --max-tasks N                  Maximum number of tasks to evaluate (default: 10)
#   --max-parallel-sessions N      Number of concurrent evaluation sessions (default: 1)
#   --plugin-preset PRESET         Plugin preset for the first run:
#                                  auth-only | ibac-only | full (default: ibac-only)
#   -h, --help                     Show this help and exit
#
# The judge is configured from the OPENAI_API_BASE / OPENAI_API_KEY environment
# variables (as in the original template).
#
# Examples:
#   ./run-ibac-comparison.sh
#   ./run-ibac-comparison.sh --model gcp/gemini-3-flash-preview --benchmark gsm8k --max-tasks 10 --max-parallel-sessions 1
#   ./run-ibac-comparison.sh --plugin-preset full

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Defaults (from the template)
MODEL="gcp/gemini-3-flash-preview"
BENCHMARK="gsm8k"
AGENT="tool_calling"
MAX_TASKS=10
MAX_PARALLEL_SESSIONS=1
PLUGIN_PRESET="ibac-only"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)
            MODEL="$2"
            shift 2
            ;;
        --benchmark)
            BENCHMARK="$2"
            shift 2
            ;;
        --agent)
            AGENT="$2"
            shift 2
            ;;
        --max-tasks)
            MAX_TASKS="$2"
            shift 2
            ;;
        --max-parallel-sessions)
            MAX_PARALLEL_SESSIONS="$2"
            shift 2
            ;;
        --plugin-preset)
            PLUGIN_PRESET="$2"
            shift 2
            ;;
        -h|--help)
            sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Error: unknown option: $1" >&2
            echo "Run '$0 --help' for usage." >&2
            exit 1
            ;;
    esac
done

# Validate the plugin preset. deploy-and-evaluate.sh accepts only these values;
# passing anything else (e.g. "auth_only" with an underscore) produces a broken
# auth pipeline rather than a clear error, so reject it up front.
case "$PLUGIN_PRESET" in
    auth-only|ibac-only|full)
        ;;
    *)
        echo "Error: invalid --plugin-preset: '$PLUGIN_PRESET'" >&2
        echo "Valid values: auth-only | ibac-only | full" >&2
        exit 1
        ;;
esac

# Experiment names derived from the params. The plugin run is suffixed with the
# preset name (e.g. "-ibac" for ibac-only) to keep names meaningful per preset.
PRESET_SUFFIX="${PLUGIN_PRESET%-only}"
EXPERIMENT_BASE="${BENCHMARK}-${MAX_TASKS}-parallel-${MAX_PARALLEL_SESSIONS}"
EXPERIMENT_PLUGIN="${EXPERIMENT_BASE}-${PRESET_SUFFIX}"

# Judge configuration (from the template environment).
: "${OPENAI_API_BASE:?OPENAI_API_BASE must be set}"
: "${OPENAI_API_KEY:?OPENAI_API_KEY must be set}"

echo "=========================================="
echo "Model:                  $MODEL"
echo "Benchmark:              $BENCHMARK"
echo "Agent:                  $AGENT"
echo "Max tasks:              $MAX_TASKS"
echo "Max parallel sessions:  $MAX_PARALLEL_SESSIONS"
echo "Plugin preset:          $PLUGIN_PRESET"
echo "Plugin experiment:      $EXPERIMENT_PLUGIN"
echo "Baseline experiment:    $EXPERIMENT_BASE"
echo "=========================================="

# Run 1: with the selected plugin preset.
"$SCRIPT_DIR/delete-all-deployments.sh"
env IBAC_JUDGE_ENDPOINT="$OPENAI_API_BASE" \
    IBAC_JUDGE_MODEL="$MODEL" \
    JUDGE_BEARER="$OPENAI_API_KEY" \
    "$SCRIPT_DIR/deploy-and-evaluate.sh" \
        --benchmark "$BENCHMARK" \
        --agent "$AGENT" \
        --model "openai/$MODEL" \
        --max-tasks "$MAX_TASKS" \
        --max-parallel-sessions "$MAX_PARALLEL_SESSIONS" \
        --plugin-preset "$PLUGIN_PRESET" \
        --experiment "$EXPERIMENT_PLUGIN"

# Run 2: baseline (no plugin preset).
"$SCRIPT_DIR/delete-all-deployments.sh"
env IBAC_JUDGE_ENDPOINT="$OPENAI_API_BASE" \
    IBAC_JUDGE_MODEL="$MODEL" \
    JUDGE_BEARER="$OPENAI_API_KEY" \
    "$SCRIPT_DIR/deploy-and-evaluate.sh" \
        --benchmark "$BENCHMARK" \
        --agent "$AGENT" \
        --model "openai/$MODEL" \
        --max-tasks "$MAX_TASKS" \
        --max-parallel-sessions "$MAX_PARALLEL_SESSIONS" \
        --experiment "$EXPERIMENT_BASE"

# Compare the two runs.
"$SCRIPT_DIR/analyze-run.sh" -c "${EXPERIMENT_PLUGIN},${EXPERIMENT_BASE}"
