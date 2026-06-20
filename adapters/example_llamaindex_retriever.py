"""Runnable example: a LlamaIndex BM25 retriever measured by the harness.

Strictly opt-in — requires `pip install llama-index-retrievers-bm25 llama-index-core`
(NOT core dependencies). It builds a LlamaIndex BM25Retriever over this repo's code
files, wraps it via `adapters.llamaindex_retriever.to_harness`, and exposes `retrieve`:

    pip install llama-index-retrievers-bm25 llama-index-core
    RAG_SOURCE_ROOTS="$PWD" python eval/run.py \\
        --retriever adapters.example_llamaindex_retriever:retrieve --label llamaindex

The point is not the number — a BM25 baseline over whole files is a rough instrument
on small code sets (see docs/METHODOLOGY.md). The point is that the harness measures
a real LlamaIndex retriever honestly, whatever the number turns out to be.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Optional, Sequence

from adapters.llamaindex_retriever import to_harness

_CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".sh"}
_SKIP = {".git", "node_modules", "venv", ".venv", ".rag-index", "__pycache__", "dist", "build", "tests"}
_retriever = None


def _build():
    try:
        from llama_index.core import Document
        from llama_index.retrievers.bm25 import BM25Retriever
    except ImportError as e:
        raise SystemExit(
            "this example needs LlamaIndex: "
            "pip install llama-index-retrievers-bm25 llama-index-core"
        ) from e

    roots = [Path(p) for p in os.environ.get("RAG_SOURCE_ROOTS", "").split(os.pathsep) if p] or [Path.cwd()]
    docs = []
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix not in _CODE_EXTS or not path.is_file() or _SKIP & set(path.parts):
                continue
            try:
                text = path.read_text(errors="ignore")
                docs.append(Document(text=text, metadata={"file_path": str(path)}))
            except OSError:
                continue
    if not docs:
        raise SystemExit("no code files found under RAG_SOURCE_ROOTS")
    return BM25Retriever.from_defaults(nodes=[d.as_node() for d in docs], similarity_top_k=5)


def retrieve(query: str, top: int, scope: Optional[str] = None) -> Sequence[Mapping]:
    global _retriever
    if _retriever is None:
        _retriever = _build()
    return to_harness(_retriever, similarity_top_k=top)(query, top, scope)
