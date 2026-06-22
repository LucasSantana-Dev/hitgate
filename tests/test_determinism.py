"""Prove the retrieval pipeline is deterministic.

If evaluation is non-deterministic, the numbers can't be trusted — a Hit@5 of
0.833 means nothing if re-running the same query against the same index can
reorder the results. This test proves they can be trusted: it runs every demo
query twice against the same index and asserts the top-K ordering is identical.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
from ragcore.retrieval import search

DATASET = ROOT / "hitgate" / "golden.demo.jsonl"
TOP = 5
RUNS = 2


def _fingerprint(query: str, scope) -> list[tuple[str, int]]:
    """Ordered (path, start_line) of the top-K results — the thing that must not drift."""
    results = search(query, top=TOP, scope_types=scope, scope_repos=["all"], cwd=None, rerank=False)
    return [(r["path"], r["start_line"]) for r in results]


def load_demo_cases():
    """Load determinism test cases from golden.demo.jsonl."""
    if not DATASET.exists():
        pytest.skip(f"golden.demo.jsonl not found at {DATASET}")
    cases = [
        json.loads(line)
        for line in DATASET.read_text().splitlines()
        if line.strip() and "expect_path_contains" in json.loads(line)
    ]
    if not cases:
        pytest.skip(f"no determinism test cases in {DATASET}")
    return cases


@pytest.mark.parametrize(
    "case",
    load_demo_cases(),
    ids=lambda case: case.get("query", "unknown")[:40],
)
def test_retrieval_determinism(case, tiny_index):
    """Each query must produce identical top-K ordering across multiple identical runs."""
    query = case["query"]
    scope = case.get("expect_scope")

    # Run the same query multiple times and collect top-K fingerprints
    runs = [_fingerprint(query, scope) for _ in range(RUNS)]

    # All runs must be identical
    for i, run in enumerate(runs[1:], 1):
        assert run == runs[0], (
            f"Query {query!r} produced different orderings across runs:\n"
            f"  run 0: {runs[0]}\n"
            f"  run {i}: {run}"
        )


def test_determinism_summary(tiny_index):
    """Report determinism results for all cases (summary test)."""
    cases = load_demo_cases()
    unstable = []

    for case in cases:
        query = case["query"]
        scope = case.get("expect_scope")
        runs = [_fingerprint(query, scope) for _ in range(RUNS)]
        if any(r != runs[0] for r in runs[1:]):
            unstable.append((query, runs))

    print(f"\ndeterminism: {len(cases)} queries x {RUNS} runs, top-{TOP}")
    if unstable:
        print(f"\n{len(unstable)} query(ies) produced different orderings:")
        for q, runs in unstable:
            print(f"  query: {q!r}")
            for i, r in enumerate(runs):
                print(f"    run {i}: {r}")
        pytest.fail("Non-deterministic retrieval — the eval numbers are not reproducible.")

    print(f"\nAll {len(cases)} queries stable across {RUNS} runs — eval is reproducible.")
