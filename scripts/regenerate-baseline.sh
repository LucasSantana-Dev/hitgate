#!/usr/bin/env bash
# scripts/regenerate-baseline.sh — Re-freeze eval baselines on the Linux platform.
#
# Background:
#   Baselines are frozen on CI/Ubuntu to ensure consistent gating across developers.
#   macOS float ops differ ~2pp from Linux; local evals will show drift that is NOT
#   a regression, just cross-platform variance.
#
# Usage on Linux:
#   bash scripts/regenerate-baseline.sh
#   This builds the index + runs both eval gates, then copies the results into
#   hitgate/baseline.example.json and hitgate/baseline.auto-rerank.json.
#
# Usage on non-Linux (macOS, etc.):
#   bash scripts/regenerate-baseline.sh
#   Prints guidance to use the GitHub workflow instead (recommended).
#
# Escape hatch: if you must regenerate on a non-Linux platform, set FORCE=1:
#   FORCE=1 bash scripts/regenerate-baseline.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HITGATE_DIR="$REPO_ROOT/hitgate"

# Check platform unless forced.
if [ "${FORCE:-0}" != "1" ]; then
    if [[ ! "$OSTYPE" =~ ^linux ]]; then
        cat >&2 <<'EOF'
This script is designed to run on Linux (Ubuntu). Your platform shows cross-platform
float variance (~2pp drift) compared to the CI baselines. To re-freeze baselines:

  1. Preferred: Use the GitHub workflow (manually dispatch):
     gh workflow run regenerate-baseline.yml --repo=LucasSantana-Dev/evidence-first-rag
     Then download the artifact and commit the result.

  2. Alternative: Download the eval-results artifact from a recent eval-gate run:
     - Go to the PR or main-branch CI run.
     - Download "eval-results".
     - Commit the JSONs as hitgate/baseline.example.json and hitgate/baseline.auto-rerank.json.

  3. Emergency (force on local platform):
     FORCE=1 bash scripts/regenerate-baseline.sh
     This will work but expect ~2pp drift vs CI if you're on macOS. The gate may
     fail locally even though CI would pass, until next CI freeze.

EOF
        exit 1
    fi
fi

echo "Re-freezing baselines on Linux..."

# Build index if missing.
if [ ! -f "$REPO_ROOT/.rag-index/index.sqlite" ]; then
    echo "Building index..."
    python3 "$REPO_ROOT/ragcore/build.py"
fi

# Run rerank-off baseline.
echo "Running eval gate (rerank-off)..."
bash "$HITGATE_DIR/check.sh" ci

# Copy result to baseline.
echo "Freezing baseline.example.json..."
cp "$HITGATE_DIR/ci.json" "$HITGATE_DIR/baseline.example.json"

# Run auto-rerank baseline.
echo "Running eval gate (auto-rerank)..."
RAG_RERANK_AUTO=on EVAL_EXTRA_FLAGS=--auto-rerank RAG_EVAL_BASELINE="$HITGATE_DIR/baseline.auto-rerank.json" \
    bash "$HITGATE_DIR/check.sh" auto-rerank-ci

# Copy result to baseline.
echo "Freezing baseline.auto-rerank.json..."
cp "$HITGATE_DIR/auto-rerank-ci.json" "$HITGATE_DIR/baseline.auto-rerank.json"

echo "Done. Baselines frozen:"
echo "  - $HITGATE_DIR/baseline.example.json"
echo "  - $HITGATE_DIR/baseline.auto-rerank.json"
