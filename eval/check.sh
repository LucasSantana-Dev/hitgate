#!/usr/bin/env bash
# eval/check.sh — run the eval suite and compare against baseline.json.
# Exit 0 if delta within tolerance, 1 if any metric regresses by >5pp.
# Designed to be called manually or chained from build.py after full reindex.
#
# NOTE: this gate compares aggregate metrics only — not per-intent breakdowns.
# Per-intent (by_intent) metrics are printed by run.py for visibility but are
# not gated here. See docs/adr/0003-per-intent-ci-gating-deferred.md for why
# and the exact trigger conditions that would change this.
set -uo pipefail

EVAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$EVAL_DIR/.." && pwd)"
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
"$PY" run.py --dataset "$DATASET" --label "$LABEL" >/tmp/eval-run.out 2>&1
status=$?
cat /tmp/eval-run.out
[ "$status" -ne 0 ] && exit "$status"

CURRENT="$EVAL_DIR/${LABEL}.json"
BASELINE="${RAG_EVAL_BASELINE:-$EVAL_DIR/baseline.example.json}"
[ -f "$BASELINE" ] || { echo "(no baseline at $BASELINE — skipping comparison)"; exit 0; }
[ -f "$CURRENT" ]  || { echo "(no $CURRENT — eval may have failed)"; exit 1; }

"$PY" - "$CURRENT" "$BASELINE" "$TOL_PP" <<'PY'
import json, sys
cur, base, tol_pp = sys.argv[1:]
cur_j  = json.loads(open(cur).read())
base_j = json.loads(open(base).read())
tol = float(tol_pp) / 100.0
metrics = ("mrr", "hit@1", "hit@3", "hit@5")
regressions = []
print(f"\nDelta vs baseline (tolerance ±{tol_pp}pp):")
for m in metrics:
    delta = cur_j[m] - base_j[m]
    arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "·")
    flag  = "  ⚠ REGRESSION" if delta < -tol else ""
    print(f"  {m:<8} {base_j[m]:.3f} → {cur_j[m]:.3f}  {arrow}{abs(delta):+.3f}{flag}")
    if delta < -tol:
        regressions.append(m)
if regressions:
    print(f"\nRegressed: {', '.join(regressions)} — investigate before shipping retrieval changes.")
    sys.exit(1)
print("\n✓ within tolerance.")
PY
