"""Opt-in adapter: measure a LangChain retriever with the evidence-first-rag harness.

This file has **no hard dependency** — it duck-types the LangChain interface, so it imports
even when LangChain isn't installed. It turns any LangChain retriever (anything exposing
`.invoke(query)` or `.get_relevant_documents(query)` returning Documents with `.metadata` /
`.page_content`) into the harness protocol:

    retrieve(query, top, scope) -> list[{"path": ...}]

Wire it up in a tiny module that builds your retriever and exposes the callable, then point
the gate at it:

    python -m hitgate.run --retriever yourmod:retrieve

A runnable example using LangChain's BM25Retriever is in
`adapters/example_langchain_retriever.py`. See `adapters/README.md`.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Optional, Sequence


def to_harness(lc_retriever: Any, path_key: str = "source") -> Callable[[str, int, Optional[str]], Sequence[Mapping]]:
    """Wrap a LangChain retriever as a harness retriever.

    path_key: the metadata key holding the document's path/identifier (LangChain loaders
    conventionally use "source"). Falls back to the document's page_content if absent.
    """
    def retrieve(query: str, top: int, scope: Optional[str] = None) -> Sequence[Mapping]:
        if hasattr(lc_retriever, "invoke"):
            docs = lc_retriever.invoke(query)
        else:  # older LangChain
            docs = lc_retriever.get_relevant_documents(query)
        results = []
        for d in list(docs)[:top]:
            meta = getattr(d, "metadata", None) or {}
            path = meta.get(path_key) or getattr(d, "page_content", "")
            results.append({"path": str(path)})
        return results

    return retrieve
