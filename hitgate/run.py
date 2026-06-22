#!/usr/bin/env python3
"""Evaluate retrieval quality against a curated Q/A dataset — for ANY retriever.

This is the harness: a label-free, regression-gated quality check you can point at your
own retriever, not just the bundled one. A retriever is any callable

    retrieve(query: str, top: int, scope: str | None) -> Sequence[Mapping]

returning results ranked best-first, each a mapping with at least a "path" key (and
optionally "start_line"). Rank is assigned by position, so an external retriever doesn't
compute it. The harness scores Hit@1/@3/@5 + MRR by where the expected path first appears
and writes hitgate/<label>.json.

Inputs:  hitgate/golden.demo.jsonl  (one JSON per line: query, expect_path_contains, expect_scope)

Usage:
  python -m hitgate.run                                            # bundled retriever, demo set
  python -m hitgate.run --label wider --top 10
  python -m hitgate.run --rerank                                   # bundled + cross-encoder rerank
  python -m hitgate.run --retriever mypkg.myretriever:retrieve     # YOUR retriever (see adapters/)
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from hitgate import Retriever

ROOT = Path(__file__).resolve().parent.parent

DATASET = ROOT / "hitgate" / "golden.demo.jsonl"


def builtin_retriever(rerank: Optional[bool] = False) -> Retriever:
    """The bundled hybrid retriever (ragcore), wrapped to the harness protocol.

    rerank=False  — never rerank (default eval baseline)
    rerank=True   — always rerank (forced; use --rerank flag)
    rerank=None   — auto-trigger path: fires on weak/ambiguous queries (use --auto-rerank flag)
    """
    from ragcore.retrieval import search

    def _retrieve(query: str, top: int, scope: Optional[str]) -> Sequence[Mapping]:
        return search(query, top=top, scope_types=scope, scope_repos=["all"], cwd=None, rerank=rerank)

    return _retrieve


def load_retriever(spec: Optional[str], rerank: Optional[bool] = False) -> Retriever:
    """Resolve --retriever: None -> bundled; 'module.path:callable' -> imported callable."""
    if not spec:
        return builtin_retriever(rerank)
    mod_name, sep, func_name = spec.partition(":")
    if not sep or not mod_name or not func_name:
        sys.exit(f"--retriever must be 'module.path:callable', got {spec!r}")
    try:
        fn = getattr(importlib.import_module(mod_name), func_name)
    except (ImportError, AttributeError) as e:
        sys.exit(f"could not load retriever {spec!r}: {e}")
    if not callable(fn):
        sys.exit(f"retriever {spec!r} is not callable")
    return fn


def load(path: Path = DATASET) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _validate_retriever_result(result: object, query: str) -> None:
    """Validate that a retriever result is a mapping with a string 'path' key.
    
    Raises:
        TypeError: if result is not a mapping, or 'path' is not a string.
        ValueError: if result is missing the required 'path' key.
    """
    if not isinstance(result, dict):
        raise TypeError(
            f"External retriever returned malformed result for query {query!r}: "
            f"expected a mapping (dict), got {type(result).__name__}: {result!r}"
        )
    if "path" not in result:
        raise ValueError(
            f"External retriever returned result missing required 'path' key for query {query!r}. "
            f"Each result must be a dict with at least 'path' (str). Got: {result!r}"
        )
    if not isinstance(result["path"], str):
        raise TypeError(
            f"External retriever returned result with non-string 'path' for query {query!r}: "
            f"'path' must be str, got {type(result['path']).__name__}: {result!r}"
        )


def run(cases: list[dict], top: int, retriever: Retriever) -> dict:
    per_case = []
    for case in cases:
        # Tolerate the legacy diff-scoped schema (id/type/expected_files) by skipping it.
        if "expect_path_contains" not in case:
            continue
        q = case["query"]
        expect = case["expect_path_contains"]
        scope = case.get("expect_scope")
        scope_key = scope if isinstance(scope, str) and scope else ("+".join(scope) if isinstance(scope, list) and scope else "none")
        expected = expect if isinstance(expect, list) else [expect]
        results = list(retriever(q, top, scope if isinstance(scope, str) else None))
        # Validate each result before processing
        for r in results:
            _validate_retriever_result(r, q)
        hit_rank = None
        for rank, r in enumerate(results, 1):  # rank by position — retriever-agnostic
            if any(e in r["path"] for e in expected):
                hit_rank = rank
                break
        top_hit = f"{results[0]['path']}:{results[0].get('start_line', '?')}" if results else None
        intent = case.get("intent", "unclassified")
        per_case.append(
            {"query": q, "expect": expect, "scope": scope_key, "intent": intent, "hit_rank": hit_rank, "top_hit": top_hit}
        )

    def metrics(cases: list[dict]) -> dict:
        n = len(cases) or 1
        hits_at = lambda k: sum(1 for c in cases if c["hit_rank"] and c["hit_rank"] <= k) / n
        mrr = sum((1.0 / c["hit_rank"]) if c["hit_rank"] else 0.0 for c in cases) / n
        return {
            "n": len(cases),
            "mrr": round(mrr, 3),
            "hit@1": round(hits_at(1), 3),
            "hit@3": round(hits_at(3), 3),
            "hit@5": round(hits_at(5), 3),
        }

    by_scope: dict[str, list] = {}
    for c in per_case:
        by_scope.setdefault(c["scope"], []).append(c)

    by_intent: dict[str, list] = {}
    for c in per_case:
        by_intent.setdefault(c["intent"], []).append(c)

    out = metrics(per_case)
    out["by_scope"] = {sc: metrics(cs) for sc, cs in sorted(by_scope.items())}
    out["by_intent"] = {it: metrics(cs) for it, cs in sorted(by_intent.items())}
    out["per_case"] = per_case
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--label", default="baseline")
    ap.add_argument("--dataset", default=str(DATASET), help="path to eval dataset jsonl")
    ap.add_argument("--retriever", default=None, help="'module.path:callable' for your own retriever (default: bundled)")
    ap.add_argument("--rerank", action="store_true", help="force cross-encoder reranking on all queries (bundled retriever only)")
    ap.add_argument("--auto-rerank", action="store_true", help="use auto-trigger reranking (rerank=None path; fires on weak/ambiguous queries)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    rerank_mode: Optional[bool] = None if args.auto_rerank else (True if args.rerank else False)
    retriever = load_retriever(args.retriever, rerank=rerank_mode)
    cases = load(Path(args.dataset))
    started = time.time()
    result = run(cases, top=args.top, retriever=retriever)
    elapsed = time.time() - started

    tag = f" [{args.retriever}]" if args.retriever else (" [AUTO-RERANK]" if args.auto_rerank else (" [RERANK]" if args.rerank else " [FAST]"))
    print(
        f"[{args.label}]{tag}  n={result['n']}  MRR={result['mrr']}  "
        f"hit@1={result['hit@1']}  hit@3={result['hit@3']}  hit@5={result['hit@5']}  "
        f"({elapsed:.1f}s)"
    )
    for sc, m in result.get("by_scope", {}).items():
        print(f"    scope={sc:10} n={m['n']:>3}  hit@1={m['hit@1']}  hit@5={m['hit@5']}  mrr={m['mrr']}")
    for it, m in result.get("by_intent", {}).items():
        print(f"    intent={it:14} n={m['n']:>3}  hit@1={m['hit@1']}  hit@5={m['hit@5']}  mrr={m['mrr']}")
    if args.verbose:
        for c in result["per_case"]:
            status = "✓" if c["hit_rank"] else "✗"
            rank = f"#{c['hit_rank']}" if c["hit_rank"] else "MISS"
            print(f"  {status} {rank:>4}  {c['query'][:60]}  → {c['top_hit']}")
    out_path = ROOT / "hitgate" / f"{args.label}.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
