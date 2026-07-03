#!/usr/bin/env python3
"""Query the local index (config.DB) with hybrid BM25 + cosine retrieval.

Auto-scopes to the current source root when invoked from inside one, unless
`--scope-repo all` is passed. `--scope` filters by source_type.

Examples:
  query.py "how does the reranker fall back"
  query.py --top 8 --scope code "reciprocal rank fusion"
  query.py --scope-repo all "config defaults"
  query.py --format json "..."
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from retrieval import search


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="natural-language question")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--scope", default="", help="comma-separated source types")
    ap.add_argument(
        "--scope-repo",
        default="",
        help="comma-separated repo names, or 'all' to disable cwd scoping",
    )
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument(
        "--rerank",
        choices=["on", "off", "auto"],
        default="auto",
        help="cross-encoder reranker (auto = on unless --fast)",
    )
    ap.add_argument("--fast", action="store_true", help="disable reranker for speed")
    args = ap.parse_args()
    rerank = None
    if args.rerank == "on":
        rerank = True
    elif args.rerank == "off" or args.fast:
        rerank = False

    scope_types = [s.strip() for s in args.scope.split(",") if s.strip()] or None
    if args.scope_repo == "all":
        scope_repos = None
        cwd = None
    elif args.scope_repo:
        scope_repos = [s.strip() for s in args.scope_repo.split(",") if s.strip()]
        cwd = None
    else:
        scope_repos = None
        cwd = None  # let cwd_repo() detect

    results = search(
        args.query,
        top=args.top,
        scope_types=scope_types,
        scope_repos=scope_repos,
        cwd=cwd,
        rerank=rerank,
    )

    if args.format == "json":
        print(json.dumps(results, indent=2))
        return 0

    if not results:
        print("(no matches)")
        return 1
    for r in results:
        tag = f"{r['source_type']}"
        if r.get("repo"):
            tag += f"/{r['repo']}"
        if r.get("symbol"):
            tag += f"::{r['symbol']}"
        print(
            f"#{r['rank']}  rrf={r['rrf']} cos={r['cos']} bm={r['bm25']}  [{tag}]  {r['path']}:{r['start_line']}-{r['end_line']}"
        )
        snippet = r["text"][:400].replace("\n", " ")
        print(f"   {snippet}{'…' if len(r['text']) > 400 else ''}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
