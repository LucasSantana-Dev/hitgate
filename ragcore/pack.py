#!/usr/bin/env python3
"""Build a task-aware context pack: relevant code + standards + past decisions.

Input:   task description (positional) + optional --files <paths> (e.g. git diff).
Output:  a Markdown bundle on stdout, capped at --budget tokens (~4 chars/token).

Usage:
  pack.py "add retry logic to the indexer"
  pack.py --files ragcore/retrieval.py "explain the fusion step"
  pack.py --budget 3000 "where are config defaults set"
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from retrieval import search, cwd_repo


def approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def pack(task: str, files: list[str], budget_tokens: int, cwd: str | None) -> str:
    budget = budget_tokens
    out: list[str] = []

    def emit(header: str, chunks: list[dict], per_chunk_cap: int) -> None:
        nonlocal budget
        if not chunks:
            return
        out.append(f"## {header}")
        for r in chunks:
            snippet = r["text"][:per_chunk_cap]
            sym = f"::{r['symbol']}" if r.get("symbol") else ""
            repo = f"/{r['repo']}" if r.get("repo") else ""
            header_line = f"### {r['source_type']}{repo}{sym}  `{r['path']}:{r['start_line']}-{r['end_line']}`  (cos={r['cos']} bm={r['bm25']})"
            block = f"{header_line}\n```\n{snippet}\n```\n"
            cost = approx_tokens(block)
            if budget - cost < 0:
                return
            out.append(block)
            budget -= cost
        out.append("")

    # 1. Direct code chunks in the task's repo
    code_hits = search(task, top=6, scope_types=["code"], cwd=cwd)
    emit("Relevant code", code_hits, per_chunk_cap=900)

    # 2. Explicit files: include the file's top-1 symbol chunks matched against task
    if files:
        out.append("## Explicit files")
        for f in files:
            p = Path(f).expanduser().resolve()
            hits = search(task, top=2, scope_types=["code"], scope_repos=["all"], cwd=cwd)
            hits = [h for h in hits if h["path"] == str(p)]
            if not hits:
                # Fall back: read the file header (first 40 lines)
                if p.is_file():
                    head = "\n".join(p.read_text(errors="replace").splitlines()[:40])
                    block = f"### {p.name}  `{p}:1-40`\n```\n{head}\n```\n"
                    cost = approx_tokens(block)
                    if budget - cost >= 0:
                        out.append(block)
                        budget -= cost
                continue
            for r in hits:
                snippet = r["text"][:900]
                block = f"### {r['path']}:{r['start_line']}-{r['end_line']}\n```\n{snippet}\n```\n"
                cost = approx_tokens(block)
                if budget - cost < 0:
                    break
                out.append(block)
                budget -= cost
        out.append("")

    if not out:
        return "(no relevant context found)"
    header = f"# Context pack for: {task}\n_Budget: {budget_tokens} tokens · remaining ≈ {budget}_\n"
    return header + "\n" + "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", help="task description in natural language")
    ap.add_argument("--files", nargs="*", default=[], help="paths to touched files")
    ap.add_argument("--diff", action="store_true", help="use `git diff --name-only` as --files")
    ap.add_argument("--budget", type=int, default=4000, help="token budget (chars/4)")
    ap.add_argument("--cwd", default=None)
    args = ap.parse_args()

    files = list(args.files)
    if args.diff:
        try:
            proc = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True,
                text=True,
                check=True,
            )
            files.extend([f for f in proc.stdout.splitlines() if f])
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    print(pack(args.task, files, args.budget, args.cwd))
    return 0


if __name__ == "__main__":
    sys.exit(main())
