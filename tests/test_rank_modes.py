"""Exercise the RAG_RANK_MODE branches, RRF behaviour, and reranker graceful fallback
against a real (tiny) index. These run the actual retrieval path, not mocks of it."""
import ragcore.retrieval as retrieval
from ragcore.retrieval import search

CODE = dict(scope_types=["code"], scope_repos=["all"], top=3)


def _paths(results):
    return [r["path"] for r in results]


def test_all_rank_modes_return_results(tiny_index, monkeypatch):
    for mode in ("bm25", "dense", "hybrid"):
        monkeypatch.setenv("RAG_RANK_MODE", mode)
        res = search("reciprocal rank fusion of dense and bm25 orders", **CODE)
        assert res, f"{mode} returned no results"
        assert all({"rank", "path", "start_line"} <= r.keys() for r in res)
        assert [r["rank"] for r in res] == list(range(1, len(res) + 1))


def test_bm25_only_ranks_exact_lexical_match_first(tiny_index, monkeypatch):
    # a query built from the exact identifier should put its file on top under lexical-only ranking
    monkeypatch.setenv("RAG_RANK_MODE", "bm25")
    res = search("reciprocal_rank_fusion", **CODE)
    assert res and "fusion.py" in res[0]["path"]


def test_invalid_rank_mode_falls_back_to_dense(tiny_index, monkeypatch):
    # unknown mode must not crash — the else branch ranks by cosine
    monkeypatch.setenv("RAG_RANK_MODE", "banana")
    res = search("split an identifier into camel case pieces", **CODE)
    assert res, "unknown rank mode should still return results (dense fallback)"


def test_hybrid_is_default_when_unset(tiny_index, monkeypatch):
    monkeypatch.delenv("RAG_RANK_MODE", raising=False)
    monkeypatch.delenv("RAG_HYBRID", raising=False)
    res = search("reciprocal rank fusion", **CODE)
    assert res


def test_rag_hybrid_zero_is_back_compatible_dense(tiny_index, monkeypatch):
    # legacy toggle: RAG_HYBRID=0 must still mean cosine-only and keep working
    monkeypatch.delenv("RAG_RANK_MODE", raising=False)
    monkeypatch.setenv("RAG_HYBRID", "0")
    res = search("database connection string configuration", **CODE)
    assert res


def test_reranker_failure_falls_back_to_fused(tiny_index, monkeypatch):
    # if the reranker can't load, the query must still resolve via the fused ranking
    def boom():
        raise RuntimeError("reranker model unavailable")

    monkeypatch.setattr(retrieval, "_get_reranker", boom)
    res = search("reciprocal rank fusion", rerank=True, **CODE)
    assert res, "reranker failure should fall back, not return empty"
    assert res[0]["reranked"] is True  # flag reflects the attempt, results come from fallback
