#!/usr/bin/env python3
"""compare.py — compare two eval result JSON files and emit a structured verdict.

Usage:
    python hitgate/compare.py <current.json> <baseline.json> [tol_pp=5]

Prints the human-readable delta table to stdout (same format as before).
Writes <current>.verdict.json alongside the current result.
Exits 0 if verdict is pass or improvement, 1 if regression.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def compare(cur_j: dict, base_j: dict, tol_pp: float = 5.0) -> dict:
    """Core comparison. Returns verdict dict; does not touch the filesystem."""
    tol = tol_pp / 100.0
    metrics = ("mrr", "hit@1", "hit@3", "hit@5")

    regressions: list[dict] = []
    improvements: list[dict] = []
    deltas: dict[str, float] = {}

    for m in metrics:
        delta = round(cur_j[m] - base_j[m], 4)
        deltas[m] = delta
        if delta < -tol:
            regressions.append({"metric": m, "scope": "aggregate", "delta": delta})
        elif delta > tol:
            improvements.append({"metric": m, "scope": "aggregate", "delta": delta})

    base_intent = base_j.get("by_intent", {})
    cur_intent = cur_j.get("by_intent", {})
    for intent in sorted(base_intent):
        if intent not in cur_intent:
            continue
        b5 = base_intent[intent].get("hit@5")
        c5 = cur_intent[intent].get("hit@5")
        if b5 is None or c5 is None:
            continue
        delta = round(c5 - b5, 4)
        scope = f"intent:{intent}"
        if delta < -tol:
            regressions.append({"metric": "hit@5", "scope": scope, "delta": delta})
        elif delta > tol:
            improvements.append({"metric": "hit@5", "scope": scope, "delta": delta})

    refreeze = any(
        r["metric"] == "hit@5" and r["scope"] == "aggregate" for r in improvements
    )

    if regressions:
        verdict = "regression"
    elif refreeze:
        verdict = "improvement"
    else:
        verdict = "pass"

    return {
        "verdict": verdict,
        "gated_metric": "hit@5",
        "tolerance_pp": tol_pp,
        "regressions": regressions,
        "improvements": improvements,
        "deltas": deltas,
        "refreeze_recommended": refreeze,
    }


def print_table(cur_j: dict, base_j: dict, v: dict, tol_pp: float) -> None:
    """Human-readable delta table — same format as the old check.sh heredoc."""
    metrics = ("mrr", "hit@1", "hit@3", "hit@5")
    print(f"\nDelta vs baseline (tolerance ±{tol_pp}pp):")
    for m in metrics:
        delta = cur_j[m] - base_j[m]
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "·")
        flag = (
            "  ⚠ REGRESSION"
            if any(r["metric"] == m and r["scope"] == "aggregate" for r in v["regressions"])
            else ""
        )
        print(f"  {m:<8} {base_j[m]:.3f} → {cur_j[m]:.3f}  {arrow}{abs(delta):+.3f}{flag}")

    base_intent = base_j.get("by_intent", {})
    cur_intent = cur_j.get("by_intent", {})
    if base_intent and cur_intent:
        print(f"\nPer-intent Hit@5 (tolerance ±{tol_pp}pp):")
        for intent in sorted(base_intent):
            if intent not in cur_intent:
                continue
            b5 = base_intent[intent].get("hit@5")
            c5 = cur_intent[intent].get("hit@5")
            if b5 is None or c5 is None:
                continue
            delta = c5 - b5
            n = cur_intent[intent].get("n", "?")
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "·")
            scope = f"intent:{intent}"
            flag = (
                "  ⚠ REGRESSION"
                if any(r["scope"] == scope for r in v["regressions"])
                else ""
            )
            print(f"  {intent:<16} n={n}  {b5:.3f} → {c5:.3f}  {arrow}{abs(delta):+.3f}{flag}")

    if v["regressions"]:
        names = [
            r["metric"] if r["scope"] == "aggregate" else r["scope"]
            for r in v["regressions"]
        ]
        print(f"\nRegressed: {', '.join(names)} — investigate before shipping retrieval changes.")
        return

    if v["refreeze_recommended"]:
        print("\n✓ within tolerance. Hit@5 improved — consider re-freezing the baseline.")
    else:
        print("\n✓ within tolerance.")


def main() -> int:
    if len(sys.argv) < 3:
        sys.exit(f"Usage: {sys.argv[0]} <current.json> <baseline.json> [tol_pp=5]")

    cur_path = Path(sys.argv[1])
    base_path = Path(sys.argv[2])
    tol_pp = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0

    cur_j = json.loads(cur_path.read_text())
    base_j = json.loads(base_path.read_text())

    v = compare(cur_j, base_j, tol_pp)
    print_table(cur_j, base_j, v, tol_pp)

    verdict_path = cur_path.with_suffix("").parent / (cur_path.stem + ".verdict.json")
    verdict_path.write_text(json.dumps(v, indent=2))

    return 1 if v["verdict"] == "regression" else 0


if __name__ == "__main__":
    sys.exit(main())
