#!/usr/bin/env python3
"""A minimal, dependency-free example retriever — the template for "bring your own".

It implements the harness protocol:  retrieve(query, top, scope) -> list[dict].
This one is deliberately dumb (ranks files by how many distinct query words they contain —
no embeddings, no index) to prove the harness measures ANY retriever, not just the bundled
hybrid one. Score it through the exact same eval:

    RAG_SOURCE_ROOTS="$PWD" python eval/run.py --retriever eval.example_external_retriever:retrieve

To wire your own retriever, copy this signature and return results ranked best-first, each a
mapping with a "path" (and optionally "start_line"). See adapters/ for ecosystem wrappers.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]+")
_CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".sh"}
_SKIP_PARTS = {".git", "node_modules", "venv", ".venv", ".rag-index", "__pycache__", "dist", "build"}


def _roots() -> list[Path]:
    raw = os.environ.get("RAG_SOURCE_ROOTS", "")
    return [Path(p) for p in raw.split(os.pathsep) if p] or [Path.cwd()]


def retrieve(query: str, top: int, scope: str | None = None) -> list[dict]:
    """Rank files by how many distinct query terms appear in them. Best-first, top-`top`."""
    terms = {w.lower() for w in _WORD.findall(query)}
    scored: list[tuple[int, str]] = []
    for root in _roots():
        for path in root.rglob("*"):
            if path.suffix not in _CODE_EXTS or not path.is_file():
                continue
            if _SKIP_PARTS & set(path.parts):
                continue
            try:
                text = path.read_text(errors="ignore").lower()
            except OSError:
                continue
            score = sum(1 for t in terms if t in text)
            if score:
                scored.append((score, str(path)))
    scored.sort(key=lambda s: -s[0])
    return [{"path": p, "start_line": 1} for _, p in scored[:top]]
