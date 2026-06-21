#!/usr/bin/env python3
"""hitgate/test_determinism.py — prove the retrieval pipeline is deterministic.

If evaluation is non-deterministic, the numbers can't be trusted — a Hit@5 of
0.833 means nothing if re-running the same query against the same index can
reorder the results. This gate proves they can be trusted: it runs every demo
query twice against the same index and asserts the top-K ordering is identical.

Exit 0 if every query is stable, 1 if any ordering drifts. No baseline file, no
model download beyond what build.py already cached — just same-input/same-output.

Usage:
  RAG_SOURCE_ROOTS="$PWD" python -m ragcore.build     # build the index first
  RAG_SOURCE_ROOTS="$PWD" python -m hitgate.test_determinism
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
from ragcore.retrieval import search

DATASET = ROOT / "hitgate" / "golden.demo.jsonl"
TOP = 5
RUNS = 2


def _fingerprint(query: str, scope) -> list[tuple[str, int]]:
    """Ordered (path, start_line) of the top-K results — the thing that must not drift."""
    results = search(query, top=TOP, scope_types=scope, scope_repos=["all"], cwd=None, rerank=False)
    return [(r["path"], r["start_line"]) for r in results]


def main() -> int:
    cases = [
        json.loads(line)
        for line in DATASET.read_text().splitlines()
        if line.strip() and "expect_path_contains" in json.loads(line)
    ]
    if not cases:
        print(f"no eval cases in {DATASET}", file=sys.stderr)
        return 1

    unstable = []
    for case in cases:
        q, scope = case["query"], case.get("expect_scope")
        runs = [_fingerprint(q, scope) for _ in range(RUNS)]
        if any(r != runs[0] for r in runs[1:]):
            unstable.append((q, runs))

    print(f"determinism: {len(cases)} queries x {RUNS} runs, top-{TOP}")
    if unstable:
        print(f"\n✗ {len(unstable)} query(ies) produced different orderings across identical runs:")
        for q, runs in unstable:
            print(f"  query: {q!r}")
            for i, r in enumerate(runs):
                print(f"    run {i}: {r}")
        print("\nNon-deterministic retrieval — the eval numbers are not reproducible.")
        return 1

    print(f"\n✓ all {len(cases)} queries stable across {RUNS} identical runs — eval is reproducible.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
