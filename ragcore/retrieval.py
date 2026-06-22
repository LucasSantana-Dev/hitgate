"""Shared retrieval logic: hybrid BM25 + cosine with Reciprocal Rank Fusion.

Loaded once per process (sqlite read + tokenize) and cached by scope signature.
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

try:
    import numpy as np
except ImportError:  # numpy ships with the optional [hybrid] extra
    np = None  # type: ignore[assignment]
try:
    from rank_bm25 import BM25Okapi
except ImportError:  # rank-bm25 ships with the optional [hybrid] extra
    BM25Okapi = None  # type: ignore[assignment]

sys.path.insert(0, str(Path(__file__).parent))
from config import DB, QLOG, SOURCE_ROOTS, EMBED_MODEL as MODEL_NAME, EMBED_DIM as DIM, require_hybrid

RRF_K = 60
BM25_WEIGHT = float(os.environ.get("RAG_BM25_WEIGHT", "1.5"))  # >1 favors lexical (code) match

# Roots used to auto-detect the "repo" for cwd-scoped queries (from RAG_SOURCE_ROOTS).
REPO_ROOTS = SOURCE_ROOTS

_TOKEN_RE = re.compile(r"[A-Za-z_][\w$]{1,}")
_SUB_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z][a-z]+|[a-z]+|[A-Z]+|\d+")
_SYM_STOP = {"where","what","when","does","with","from","this","that","which","used","call","calls","file","files","function","defined","definition","class","interface","type","setup","how","are","the","and","for","into","across","handler","implementation","usage","schema"}
_model = None
_reranker = None
_cache: dict[tuple, tuple[list[dict], np.ndarray, BM25Okapi]] = {}
# Reranker model — two measured options (Pareto table, ROADMAP §5, 50-case golden set):
#   ms-marco-MiniLM-L-6-v2:  88MB,  30.2s/50q, Hit@1=0.62, MRR=0.746, Hit@5=0.96
#   BAAI/bge-reranker-v2-m3: 2.1GB, 194.2s/50q, Hit@1=0.82, MRR=0.875, Hit@5=0.96
# bge-v2-m3 is strictly better on quality (+20pp Hit@1) at 6.4× latency cost.
# Default stays ms-marco-L6 for portability (88MB vs 2.1GB); set
# RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3 when disk space allows.
RERANK_MODEL_DEFAULT = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANK_MODEL = os.environ.get("RAG_RERANK_MODEL", RERANK_MODEL_DEFAULT)

# Auto-rerank configuration for weak/ambiguous queries.
RERANK_AUTO = os.environ.get("RAG_RERANK_AUTO", "on").lower() in ("on", "1", "true")
RERANK_AUTO_THRESHOLD = float(os.environ.get("RAG_RERANK_AUTO_THRESHOLD", "0.35"))
# 0.015 calibrated on 50-case golden set: fires on ambiguous queries (cosine margin < 0.015)
# achieving Hit@1 +6pp (0.56→0.62) with Hit@5=1.0 maintained. Old default (0.08) caused 2 MISSes.
RERANK_AUTO_MARGIN = float(os.environ.get("RAG_RERANK_AUTO_MARGIN", "0.015"))
# Selective reranking for code-scope queries (the measured weak spot where fused ranking is
# weakest). Code retrieval is lexical-dominant; selective code-scope reranking avoids the Hit@5
# regression (1.0→0.96) observed with forced-global reranking (ADR-0011). Non-code scopes remain
# on fused ranking. Default OFF — the model is ~2.1GB and machine-local; enable (with
# RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3 + the model cached) only where present. Reranker
# failures fall back to the fused ranking (graceful).
RAG_CODE_RERANK = os.environ.get("RAG_CODE_RERANK", "off").lower() in ("on", "1", "true")


def _auto_rerank_decision(rerank: bool, top1: float, top2: float, is_code_scope: bool) -> bool:
    """Pure decision helper for auto-rerank trigger logic.

    Encapsulates lines 255–273 of search(): determines whether to enable reranking based on:
      - Low top-1 similarity (below RERANK_AUTO_THRESHOLD)
      - Ambiguous top-2 margin (below RERANK_AUTO_MARGIN)
      - Selective code-scope reranking (RAG_CODE_RERANK + code scope)
      - Global auto-rerank gate (RERANK_AUTO)

    Args:
      rerank: Initial rerank state (False when this is called; None is pre-checked in search())
      top1: Highest cosine similarity score (or 0.0 if no results)
      top2: Second-highest cosine similarity score (or 0.0 if <2 results)
      is_code_scope: Whether scope_types includes "code"

    Returns:
      True if reranking should be enabled, False otherwise.
    """
    # Auto-trigger rerank on weak/ambiguous queries (if not explicitly disabled).
    # NOTE (2026-06-15): in bge code-rerank mode, the configured reranker (RAG_RERANK_MODEL,
    # e.g. bge-reranker-v2-m3) is validated ONLY for code scope (ADR-0011). Applying it to
    # non-code scopes regresses retrieval on mixed corpora (see ADR-0011 for the qualitative
    # rationale). So in bge mode, confine ALL reranking to code scope. In default (ms-marco)
    # mode, auto-rerank fires on any scope as before (it was net-positive there).
    auto_allowed = RERANK_AUTO and (not RAG_CODE_RERANK or is_code_scope)
    if not rerank and auto_allowed:
        if top1 < RERANK_AUTO_THRESHOLD or (top1 - top2) < RERANK_AUTO_MARGIN:
            rerank = True
    # Selective code-scope rerank (ADR 0011): the fused ranking is weakest for code.
    if not rerank and RAG_CODE_RERANK and is_code_scope:
        rerank = True
    return rerank


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder(RERANK_MODEL)
    return _reranker


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer, models

        try:
            _model = SentenceTransformer(MODEL_NAME)
        except TypeError as exc:
            if "embedding_dimension" not in str(exc):
                raise
            model_path = MODEL_NAME
            try:
                from huggingface_hub import snapshot_download

                model_path = snapshot_download(MODEL_NAME, local_files_only=True)
            except Exception:
                cache_root = Path.home() / ".cache" / "huggingface" / "hub"
                # Convert MODEL_NAME (intfloat/multilingual-e5-small) to cache path format
                cache_dir_name = "models--" + MODEL_NAME.replace("/", "--")
                snapshots = (
                    cache_root
                    / cache_dir_name
                    / "snapshots"
                )
                candidates = [p for p in snapshots.glob("*") if (p / "config.json").exists()]
                if candidates:
                    model_path = str(candidates[0])
            transformer = models.Transformer(model_path)
            pooling = models.Pooling(DIM, pooling_mode="mean")
            normalize = models.Normalize()
            _model = SentenceTransformer(modules=[transformer, pooling, normalize])
    return _model


def _tokenize(text: str) -> list[str]:
    # Code-aware: whole identifier (lowercased) + camelCase/snake_case/dotted sub-tokens,
    # so natural-language queries ("get user profile") match symbol names ("getUserProfile").
    # Applied to both corpus and query sides. Validated +2.8pp code / +3.2pp overall, 0 regressions.
    out: list[str] = []
    for tok in _TOKEN_RE.findall(text):
        out.append(tok.lower())
        subs: list[str] = []
        for piece in re.split(r"[_$]+", tok):
            subs.extend(_SUB_RE.findall(piece))
        subs = [s.lower() for s in subs if len(s) >= 2]
        if len(subs) > 1:
            out.extend(subs)
    return out


def cwd_repo(cwd: str | None = None) -> str | None:
    """Detect which curated repo the cwd lives in, returning the repo.name."""
    path = Path(cwd or os.getcwd()).resolve()
    for repo in REPO_ROOTS:
        try:
            path.relative_to(repo)
            return repo.name
        except ValueError:
            continue
    return None


def _load(scope_types: list[str] | None, scope_repos: list[str] | None) -> tuple:
    key = (
        tuple(sorted(scope_types)) if scope_types else None,
        tuple(sorted(scope_repos)) if scope_repos else None,
    )
    if key in _cache:
        return _cache[key]
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")  # WAL+timeout hardening (WAL set by writer)
    where: list[str] = []
    params: list[Any] = []
    if scope_types:
        where.append(f"source_type IN ({','.join('?' * len(scope_types))})")
        params.extend(scope_types)
    if scope_repos:
        where.append(f"repo IN ({','.join('?' * len(scope_repos))})")
        params.extend(scope_repos)
    sql = (
        "SELECT id, source_type, repo, language, symbol, path, start_line, end_line, text, embedding "
        "FROM chunks"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    cur = conn.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    if not rows:
        empty_meta: list[dict] = []
        empty_embs = np.zeros((0, DIM), dtype=np.float32)
        bm25 = BM25Okapi([[""]])
        _cache[key] = (empty_meta, empty_embs, bm25)
        return _cache[key]
    embs = np.frombuffer(b"".join(r[9] for r in rows), dtype=np.float32).reshape(-1, DIM)
    meta = [
        {
            "id": r[0],
            "source_type": r[1],
            "repo": r[2],
            "language": r[3],
            "symbol": r[4],
            "path": r[5],
            "start_line": r[6],
            "end_line": r[7],
            "text": r[8],
        }
        for r in rows
    ]
    tokens = [_tokenize(f"{m['symbol']} {m['text']}") for m in meta]
    bm25 = BM25Okapi(tokens)
    _cache[key] = (meta, embs, bm25)
    return _cache[key]


def search(
    query: str,
    top: int = 5,
    scope_types: list[str] | None = None,
    scope_repos: list[str] | None = None,
    cwd: str | None = None,
    rerank: bool | None = None,
) -> list[dict]:
    if not query.strip():
        return []
    require_hybrid()
    if isinstance(scope_types, str):  # defensive: a bare string would char-explode in _load's IN(...)
        scope_types = [scope_types] if scope_types else None
    if scope_repos == ["all"]:
        scope_repos = None
    elif scope_repos is None:
        detected = cwd_repo(cwd)
        if detected:
            scope_repos = [detected]
    meta, embs, bm25 = _load(scope_types, scope_repos)
    if not meta:
        return []

    # Cosine
    # E5 model requires "query: " prefix for queries
    prefixed_query = f"query: {query}"
    qv = _get_model().encode(
        [prefixed_query], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
    ).astype(np.float32)[0]
    cos = embs @ qv
    cos_order = np.argsort(-cos)

    # BM25
    q_tokens = _tokenize(query)
    bm_scores = bm25.get_scores(q_tokens) if q_tokens else np.zeros(len(meta))
    bm_order = np.argsort(-bm_scores)

    # Rank mode: hybrid (RRF of BM25+dense, default) | dense (cosine-only) | bm25 (lexical-only).
    # RAG_HYBRID=0 is kept as a back-compatible alias for dense. The single-channel modes exist so
    # the ablation in docs/METHODOLOGY.md is reproducible from real eval runs, not asserted.
    rank_mode = os.environ.get("RAG_RANK_MODE", "").strip().lower()
    if not rank_mode:
        rank_mode = "hybrid" if os.environ.get("RAG_HYBRID", "1").lower() in ("1", "on", "true") else "dense"

    if rank_mode == "hybrid":
        # Reciprocal Rank Fusion — take top (top*8, min 40) from each to bound work.
        fusion_window = min(len(meta), max(top * 16, 80))
        rrf: dict[int, float] = {}
        for rank, idx in enumerate(cos_order[:fusion_window]):
            rrf[int(idx)] = rrf.get(int(idx), 0.0) + 1.0 / (RRF_K + rank + 1)
        for rank, idx in enumerate(bm_order[:fusion_window]):
            rrf[int(idx)] = rrf.get(int(idx), 0.0) + BM25_WEIGHT / (RRF_K + rank + 1)
        # Symbol-definition boost: chunks whose defined symbol matches a query identifier get a
        # rank-0 signal — targets "where is X defined / X interface" queries (chunks.symbol is
        # populated; the symbols_* call-graph tables are not). Validated +2.8pp code, 0 regressions.
        q_idents = {t.lower() for t in _TOKEN_RE.findall(query) if len(t) >= 4 and t.lower() not in _SYM_STOP}
        if q_idents:
            for i, m in enumerate(meta):
                sym = (m.get("symbol") or "").lower()
                if sym and sym in q_idents:
                    rrf[int(i)] = rrf.get(int(i), 0.0) + 1.0 / (RRF_K + 1)
        cos_scores_for_ranking = rrf
    elif rank_mode == "bm25":
        # BM25-only: rank by lexical score alone (ablation baseline).
        cos_scores_for_ranking = {int(idx): float(bm_scores[idx]) for idx in range(len(bm_scores))}
    else:
        # dense / cosine-only: rank by cosine similarity.
        cos_scores_for_ranking = {int(idx): float(cos[idx]) for idx in range(len(cos))}

    if rerank is None:
        rerank = os.environ.get("RAG_RERANK", "off").lower() in ("on", "1", "true")
        is_code_scope = bool(scope_types and any("code" in s for s in scope_types))
        top1 = float(cos[cos_order[0]]) if len(cos_order) > 0 else 0.0
        top2 = float(cos[cos_order[1]]) if len(cos_order) > 1 else 0.0
        rerank = _auto_rerank_decision(rerank, top1, top2, is_code_scope)

    if rerank:
        candidate_k = min(len(meta), max(top * 4, 20))
        candidate_order = sorted(cos_scores_for_ranking.items(), key=lambda kv: -kv[1])[:candidate_k]
        pairs = [(query, meta[idx]["text"][:1500]) for idx, _ in candidate_order]
        try:
            ce_scores = _get_reranker().predict(pairs, show_progress_bar=False)
            reranked = sorted(
                zip(candidate_order, ce_scores), key=lambda x: -float(x[1])
            )[:top]
            fused = [(idx_score[0][0], float(idx_score[1])) for idx_score in reranked]
        except Exception as e:
            # Reranker unavailable (e.g. the code-rerank model isn't cached on this machine) ->
            # fall back to the fused ranking instead of failing the query. Keeps machines without
            # the 2.2GB model working at the floor. (ADR 0011)
            import sys
            print(f"WARN: reranker unavailable, using fused ranking: {e}", file=sys.stderr)
            fused = sorted(cos_scores_for_ranking.items(), key=lambda kv: -kv[1])[:top]
    else:
        fused = sorted(cos_scores_for_ranking.items(), key=lambda kv: -kv[1])[:top]

    results: list[dict] = []
    for rank, (idx, score) in enumerate(fused, 1):
        m = meta[idx]
        results.append(
            {
                "rank": rank,
                "rrf": round(float(score), 4),
                "cos": round(float(cos[idx]), 3),
                "bm25": round(float(bm_scores[idx]), 2),
                "reranked": rerank,
                "source_type": m["source_type"],
                "repo": m["repo"],
                "language": m["language"],
                "symbol": m["symbol"],
                "path": m["path"],
                "start_line": m["start_line"],
                "end_line": m["end_line"],
                "text": m["text"],
            }
        )
    if os.environ.get("RAG_QLOG", "on").lower() in ("on", "1", "true"):
        _log_query(query, scope_types, scope_repos, cwd, rerank, results)
    return results


def _log_query(
    query: str,
    scope_types: list[str] | None,
    scope_repos: list[str] | None,
    cwd: str | None,
    rerank: bool,
    results: list[dict],
) -> None:
    try:
        conn = sqlite3.connect(QLOG, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL"); conn.execute("PRAGMA busy_timeout=10000")  # WAL+timeout hardening
        conn.execute(
            """CREATE TABLE IF NOT EXISTS queries (
                ts REAL NOT NULL,
                cwd TEXT, query TEXT, scope_types TEXT, scope_repos TEXT,
                rerank INTEGER, top_score REAL, top_path TEXT, n_results INTEGER
            )"""
        )
        top_score = float(results[0]["cos"]) if results else 0.0
        top_path = results[0]["path"] if results else ""
        conn.execute(
            "INSERT INTO queries VALUES (?,?,?,?,?,?,?,?,?)",
            (
                __import__("time").time(),
                cwd or os.getcwd(),
                query[:500],
                ",".join(scope_types or []),
                ",".join(scope_repos or []),
                1 if rerank else 0,
                top_score,
                top_path,
                len(results),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"WARN: query-log write failed: {e}", file=sys.stderr)
