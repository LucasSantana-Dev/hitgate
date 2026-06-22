"""hitgate — a label-free, regression-gated retrieval-evaluation harness.

The harness core is dependency-free; the bundled hybrid retriever it can measure
lives in `ragcore` and installs with the optional `[hybrid]` extra.
"""
from __future__ import annotations

from typing import Callable, Mapping, Optional, Protocol, Sequence, runtime_checkable


@runtime_checkable
class Retriever(Protocol):
    """A retriever callable complies with the harness protocol.

    A retriever takes (query, top, scope) and returns results ranked best-first.
    Each result is a mapping with at least a "path" key. Rank is assigned by position,
    so an external retriever doesn't compute it.
    """
    def __call__(self, query: str, top: int, scope: Optional[str] = None) -> Sequence[Mapping]:
        """Retrieve top-k results for a query, optionally scoped.

        Args:
            query: the search query
            top: maximum number of results to return (rank limit)
            scope: optional scope filter (e.g., document type, repo name)

        Returns:
            Results ranked best-first, each a dict with at least "path" (str).
        """
        ...


__all__ = ["Retriever"]
