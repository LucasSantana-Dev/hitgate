"""Opt-in adapter: measure a LlamaIndex retriever with the hitgate harness.

This file has **no hard dependency** — it duck-types the LlamaIndex interface, so it
imports even when LlamaIndex isn't installed. It turns any LlamaIndex retriever (anything
exposing `.retrieve(query)` returning NodeWithScore objects) into the harness protocol:

    retrieve(query, top, scope) -> list[{"path": ...}]

Wire it up in a tiny module that builds your retriever and exposes the callable, then
point the gate at it:

    python -m hitgate.run --retriever yourmod:retrieve

A runnable example using LlamaIndex's BM25Retriever is in
`adapters/example_llamaindex_retriever.py`. See `adapters/README.md`.
"""
from __future__ import annotations

from typing import Any, Optional

from hitgate import Retriever


def to_harness(
    li_retriever: Any,
    path_key: str = "file_path",
    similarity_top_k: Optional[int] = None,
) -> Retriever:
    """Wrap a LlamaIndex retriever as a harness retriever.

    path_key: the metadata key holding the document's path/identifier. LlamaIndex
    loaders conventionally use "file_path"; some use "source" or "file_name".
    Falls back to the node's id_ if absent.

    similarity_top_k: if set, passed to the retriever at call time (for retrievers
    that accept it as a constructor or per-call parameter). Leave None to use the
    retriever's own default.
    """
    def retrieve(query: str, top: int, scope: Optional[str] = None) -> Sequence[Mapping]:
        # LlamaIndex retrievers expose .retrieve(query_str, ...) -> List[NodeWithScore]
        # Some also accept similarity_top_k as an argument; try both calling conventions.
        try:
            nodes = li_retriever.retrieve(query, similarity_top_k=top)
        except TypeError:
            nodes = li_retriever.retrieve(query)

        results = []
        for node_with_score in list(nodes)[:top]:
            # NodeWithScore wraps a TextNode (or similar) in .node
            node = getattr(node_with_score, "node", node_with_score)
            meta = getattr(node, "metadata", None) or {}
            path = (
                meta.get(path_key)
                or meta.get("source")
                or meta.get("file_name")
                or getattr(node, "id_", "")
            )
            results.append({"path": str(path)})
        return results

    return retrieve
