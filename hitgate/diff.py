#!/usr/bin/env python3
"""Compare two eval result JSON files and report per-case rank changes.

Usage:
  python -m hitgate.diff hitgate/baseline.example.json hitgate/head.json
  python -m hitgate.diff hitgate/A.json hitgate/B.json --quiet   # summary only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def rank_label(r: int | None) -> str:
    return "MISS" if r is None else f"#{r}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Diff two eval result JSON files")
    ap.add_argument("baseline", help="baseline result JSON (before)")
    ap.add_argument("head", help="head result JSON (after)")
    ap.add_argument("--quiet", action="store_true", help="summary line only, no per-case detail")
    args = ap.parse_args()

    base = load(Path(args.baseline))
    head = load(Path(args.head))

    base_cases = {c["query"]: c for c in base.get("per_case", [])}
    head_cases = {c["query"]: c for c in head.get("per_case", [])}

    queries = list(base_cases)
    unmatched = [q for q in head_cases if q not in base_cases]

    regressed, improved, stable_1, stable_other = [], [], [], []

    for q in queries:
        bc = base_cases[q]
        hc = head_cases.get(q)
        if hc is None:
            continue
        br, hr = bc["hit_rank"], hc["hit_rank"]

        # Lower rank number = better. None (MISS) = worst.
        def rank_val(r):
            return r if r is not None else 999

        if rank_val(hr) > rank_val(br):
            regressed.append((q, bc, hc))
        elif rank_val(hr) < rank_val(br):
            improved.append((q, bc, hc))
        elif hr == 1:
            stable_1.append((q, bc, hc))
        else:
            stable_other.append((q, bc, hc))

    def fmt_case(q, bc, hc):
        intent = bc.get("intent", "?")
        br, hr = bc["hit_rank"], hc["hit_rank"]
        delta = f"{rank_label(br)}→{rank_label(hr)}"
        top_changed = bc.get("top_hit") != hc.get("top_hit")
        top_note = f"  top: {hc.get('top_hit', '?')}" if top_changed else ""
        return f"  [{intent:14}]  {delta:10}  {q[:70]}{top_note}"

    if not args.quiet:
        if regressed:
            print(f"\nREGRESSED ({len(regressed)}):")
            for item in regressed:
                print(fmt_case(*item))

        if improved:
            print(f"\nIMPROVED ({len(improved)}):")
            for item in improved:
                print(fmt_case(*item))

        total_stable = len(stable_1) + len(stable_other)
        print(f"\nSTABLE ({total_stable} cases: {len(stable_1)} at rank 1, {len(stable_other)} at rank 2-5)")

        if unmatched:
            print(f"\nNEW in head ({len(unmatched)} cases not in baseline):")
            for q in unmatched:
                hc = head_cases[q]
                print(f"  [{hc.get('intent','?'):14}]  {rank_label(hc['hit_rank']):10}  {q[:70]}")

    def delta(key: str) -> str:
        b, h = base.get(key, 0.0), head.get(key, 0.0)
        d = h - b
        sign = f"+{d:.3f}" if d >= 0 else f"{d:.3f}"
        return f"{sign} ({b} → {h})"

    verdict = "REGRESSION" if regressed and not improved else ("IMPROVEMENT" if improved and not regressed else "MIXED" if improved or regressed else "IDENTICAL")
    print(f"\n{'─'*60}")
    print(f"  Δ hit@1 : {delta('hit@1')}")
    print(f"  Δ hit@3 : {delta('hit@3')}")
    print(f"  Δ hit@5 : {delta('hit@5')}")
    print(f"  Δ mrr   : {delta('mrr')}")
    print(f"  verdict : {verdict}  ({len(improved)} improved, {len(regressed)} regressed, {len(stable_1)+len(stable_other)} stable)")
    print(f"{'─'*60}")

    return 1 if regressed else 0


if __name__ == "__main__":
    sys.exit(main())
