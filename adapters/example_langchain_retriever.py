"""Runnable example: a LangChain BM25 retriever measured by the harness.

Strictly opt-in — requires `pip install langchain-community` (NOT a core dependency). It
builds a LangChain `BM25Retriever` over this repo's code files, wraps it via
`adapters.langchain_retriever.to_harness`, and exposes `retrieve` for the gate:

    pip install langchain-community
    RAG_SOURCE_ROOTS="$PWD" python -m hitgate.run \
        --retriever adapters.example_langchain_retriever:retrieve --label langchain

On the 12-case code demo it measures `Hit@5 0.917 / Hit@1 0.75 / MRR 0.833` — slightly *above*
the bundled hybrid (0.667 / 0.833), which says more about the demo being too small and lexical
to discriminate retrievers (see docs/METHODOLOGY.md) than about either retriever. The point is
that the harness measures a real LangChain retriever honestly, whatever the number.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Optional, Sequence

from adapters.langchain_retriever import to_harness

_CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".sh"}
_SKIP = {".git", "node_modules", "venv", ".venv", ".rag-index", "__pycache__", "dist", "build", "tests"}
_retriever = None


def _build():
    try:
        from langchain_community.retrievers import BM25Retriever
    except ImportError as e:  # opt-in dependency, never required by core
        raise SystemExit(
            "this example needs LangChain: pip install langchain-community"
        ) from e
    roots = [Path(p) for p in os.environ.get("RAG_SOURCE_ROOTS", "").split(os.pathsep) if p] or [Path.cwd()]
    texts, metas = [], []
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix not in _CODE_EXTS or not path.is_file() or _SKIP & set(path.parts):
                continue
            try:
                texts.append(path.read_text(errors="ignore"))
                metas.append({"source": str(path)})
            except OSError:
                continue
    if not texts:
        raise SystemExit("no code files found under RAG_SOURCE_ROOTS")
    return BM25Retriever.from_texts(texts, metadatas=metas)


def retrieve(query: str, top: int, scope: Optional[str] = None) -> Sequence[Mapping]:
    global _retriever
    if _retriever is None:
        _retriever = _build()
    _retriever.k = max(top, 1)
    return to_harness(_retriever)(query, top, scope)
