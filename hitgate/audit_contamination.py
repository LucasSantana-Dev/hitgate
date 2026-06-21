#!/usr/bin/env python3
"""hitgate/audit_contamination.py — find un-winnable cases in an eval set.

The most insidious way a retrieval benchmark lies is *contamination*: a "golden"
case whose expected answer isn't in the indexed corpus at all. Such a case can
only ever miss, so it caps the score with a constant penalty that looks like a
quality floor — and every decision made on that number inherits the lie. (This is
the audit that moved this project's own baseline ~8pp; see DECISIONS.md.)

This script makes that audit reusable. Point it at any eval set (same schema as
hitgate/golden.demo.jsonl) and an index, and it classifies every case:

  ok             — the expected path is indexed within the case's declared scope
  scope-mismatch — the path is indexed, but only OUTSIDE the declared scope
  CONTAMINATED   — the expected path is not in the corpus at all → un-winnable

Exit 0 if no contamination, 1 if any case is un-winnable (so it can gate a build).
scope-mismatch is reported as a warning, not a failure.

Usage:
  RAG_SOURCE_ROOTS="$PWD" python -m ragcore.build          # build the index first
  RAG_SOURCE_ROOTS="$PWD" python -m hitgate.audit_contamination
  python -m hitgate.audit_contamination --dataset path/to/your.jsonl
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
from ragcore.config import DB  # honors RAG_INDEX_DIR

DEFAULT_DATASET = ROOT / "hitgate" / "golden.demo.jsonl"


def _expected_substrings(case: dict) -> list[str]:
    """Non-empty expected path substrings for a case (empties dropped — '' matches every path)."""
    raw = case["expect_path_contains"]
    raw = raw if isinstance(raw, list) else [raw]
    return [e for e in raw if isinstance(e, str) and e.strip()]


def load_cases(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"dataset not found: {path}")
    cases = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as e:
            sys.exit(f"{path}:{i}: invalid JSON — {e}")
        if "expect_path_contains" not in case:  # tolerate other schemas by skipping
            continue
        if not _expected_substrings(case):
            sys.exit(
                f"{path}:{i}: case {case.get('query', '?')!r} has empty expect_path_contains "
                f"— a malformed eval case (an empty substring matches every path). Fix the eval set."
            )
        cases.append(case)
    return cases


def load_corpus(db: Path) -> list[tuple[str, str]]:
    """(source_type, path) for every indexed chunk."""
    if not db.exists():
        sys.exit(f"no index at {db} — run ragcore/build.py first")
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT source_type, path FROM chunks").fetchall()
    finally:
        conn.close()


def classify(case: dict, corpus: list[tuple[str, str]]) -> str:
    expected = _expected_substrings(case)  # already validated non-empty in load_cases
    scope = case.get("expect_scope")
    scopes = scope if isinstance(scope, list) else ([scope] if scope else [])

    def path_matches(p: str) -> bool:
        return any(e in p for e in expected)

    anywhere = [(st, p) for st, p in corpus if path_matches(p)]
    if not anywhere:
        return "CONTAMINATED"
    if scopes and not any(st in scopes for st, _ in anywhere):
        return "scope-mismatch"
    return "ok"


def resolve_dataset(arg: str) -> Path:
    """Resolve --dataset robustly: absolute as-is; otherwise try cwd-relative (standard
    CLI behavior) and then repo-root-relative, so the tool works whether you run it from
    inside the repo or from elsewhere. Errors clearly, naming both paths tried."""
    p = Path(arg)
    if p.is_absolute():
        return p
    candidates = [Path.cwd() / arg, ROOT / arg]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    sys.exit("dataset not found — tried " + " and ".join(str(c) for c in candidates))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default=str(DEFAULT_DATASET),
                    help="eval jsonl to audit (absolute, or relative to cwd or repo root)")
    args = ap.parse_args()

    dataset = resolve_dataset(args.dataset)
    cases = load_cases(dataset)
    if not cases:
        sys.exit(f"no usable cases in {dataset}")
    corpus = load_corpus(DB)

    verdicts = {"ok": [], "scope-mismatch": [], "CONTAMINATED": []}
    for case in cases:
        verdicts[classify(case, corpus)].append(case)

    n = len(cases)
    print(f"contamination audit: {n} cases vs {len(corpus)} indexed chunks ({DB})")
    print(f"  ok:             {len(verdicts['ok'])}")
    print(f"  scope-mismatch: {len(verdicts['scope-mismatch'])}")
    print(f"  CONTAMINATED:   {len(verdicts['CONTAMINATED'])}")

    for case in verdicts["scope-mismatch"]:
        print(f"\n  ⚠ scope-mismatch: {case['query'][:70]!r}")
        print(f"      expects {case['expect_path_contains']} in scope={case.get('expect_scope')}, found only out of scope")
    for case in verdicts["CONTAMINATED"]:
        print(f"\n  ✗ CONTAMINATED: {case['query'][:70]!r}")
        print(f"      expects {case['expect_path_contains']} — not in the corpus; this case is un-winnable")

    if verdicts["CONTAMINATED"]:
        print(f"\n{len(verdicts['CONTAMINATED'])} un-winnable case(s) — remove them or fix the corpus before trusting the score.")
        return 1
    print("\n✓ no contamination — every case's answer is in the corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
