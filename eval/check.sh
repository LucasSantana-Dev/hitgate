#!/usr/bin/env bash
# eval/check.sh — run the eval suite and compare against baseline.json.
# Exit 0 if delta within tolerance, 1 if any metric regresses by >5pp.
# Designed to be called manually or chained from build.py after full reindex.
#
# Gates on:
#   - Aggregate metrics (mrr, hit@1, hit@3, hit@5)
#   - Per-intent Hit@5 for each class present in the baseline (by_intent.*.hit@5)
# See docs/adr/0003-per-intent-ci-gating-deferred.md for why per-intent gating was
# deferred and the conditions that enabled it (n≥7 per class, Hit@5=1.0 baseline).
set -uo pipefail

EVAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$EVAL_DIR/.." && pwd)"
# Resolve RAG_EVAL_BASELINE to absolute before cd changes cwd
if [ -n "${RAG_EVAL_BASELINE:-}" ] && [ "${RAG_EVAL_BASELINE:0:1}" != "/" ]; then
    RAG_EVAL_BASELINE="$REPO_ROOT/$RAG_EVAL_BASELINE"
fi
LABEL="${1:-rolling-$(date +%Y%m%d-%H%M)}"
TOL_PP="${TOL_PP:-5}"
# Interpreter is overridable (CI / venv); defaults to whatever python3 is on PATH.
PY="${PYTHON:-python3}"
# Reproduce the frozen baseline's condition (pure hybrid) unless caller overrides.
export RAG_RERANK_AUTO="${RAG_RERANK_AUTO:-off}"
# Resolve index + sources to absolute paths so this works from any CWD / fresh clone.
export RAG_INDEX_DIR="${RAG_INDEX_DIR:-$REPO_ROOT/.rag-index}"
export RAG_SOURCE_ROOTS="${RAG_SOURCE_ROOTS:-$REPO_ROOT}"

# Self-contained: build the index from the repo's own source if it isn't there yet.
if [ ! -f "$RAG_INDEX_DIR/index.sqlite" ]; then
    echo "(no index at $RAG_INDEX_DIR — building from $RAG_SOURCE_ROOTS)"
    "$PY" "$REPO_ROOT/ragcore/build.py" >/tmp/eval-build.out 2>&1 || { cat /tmp/eval-build.out; exit 1; }
fi

cd "$EVAL_DIR"
# Default to the committed demo set + frozen baseline so a fresh clone runs out of the box.
DATASET="${RAG_EVAL_DATASET:-$EVAL_DIR/golden.demo.jsonl}"
# EVAL_EXTRA_FLAGS lets callers inject additional run.py flags without modifying this script.
# Example: EVAL_EXTRA_FLAGS=--auto-rerank RAG_RERANK_AUTO=on bash eval/check.sh auto-rerank-ci
"$PY" run.py --dataset "$DATASET" --label "$LABEL" ${EVAL_EXTRA_FLAGS:-} >/tmp/eval-run.out 2>&1
status=$?
cat /tmp/eval-run.out
[ "$status" -ne 0 ] && exit "$status"

CURRENT="$EVAL_DIR/${LABEL}.json"
BASELINE="${RAG_EVAL_BASELINE:-$EVAL_DIR/baseline.example.json}"
[ -f "$BASELINE" ] || { echo "(no baseline at $BASELINE — skipping comparison)"; exit 0; }
[ -f "$CURRENT" ]  || { echo "(no $CURRENT — eval may have failed)"; exit 1; }

"$PY" "$EVAL_DIR/compare.py" "$CURRENT" "$BASELINE" "$TOL_PP"
