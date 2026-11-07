# Architecture

One page on how a query becomes a ranked list, and *why* each layer is there. References
are symbolic (`file:symbol`), not line numbers, so they survive refactors.

## Data flow

```
            ┌─────────────────────── index time ───────────────────────┐
 source     │  build.py: iter_code_sources / iter_md_sources /          │
 tree   ──► │  collect_commit_chunks  ─►  chunk_file (chunkers.py)  ─►   │ ─► sqlite
 (code+     │  embed() [e5-small]  +  store text for BM25               │   .rag-index/
  docs+     │  rows: chunks(source_type, repo, language, symbol, path,  │   index.sqlite
  commits)  │  text, file_sha)  — schema in build.py:SCHEMA             │
            └──────────────────────────────────────────────────────────┘

            ┌─────────────────────── query time ───────────────────────┐
 query  ──► │  retrieval.py:search()                                    │ ─► ranked
            │    1. dense:  e5-small cosine over embeddings             │   [(path,
            │    2. lexical: BM25 over code-aware tokens                 │    start_line,
            │    3. fuse:   Reciprocal Rank Fusion (RRF_K)              │    score), …]
            │    4. rerank: optional cross-encoder, code-scoped,        │
            │               graceful fallback if absent                 │
            └──────────────────────────────────────────────────────────┘
```

Surfaces over `search()`: `query.py` (CLI), `mcp_server.py` (MCP `rag_query`), `pack.py`
(context packing), `hitgate/run.py` (Hit@K/MRR).

## Why each layer

**Hybrid (dense + lexical), not either alone.** Dense embeddings (`config.py:EMBED_MODEL`,
`intfloat/multilingual-e5-small`) catch paraphrase — "how does the reranker fall back" ↔
the relevant code with no shared words. BM25 catches the exact-token cases dense models
blur — a specific identifier or error string. Each covers the other's worst case, so the
system fuses both rather than betting on one.

**Code-aware tokenizer** (`retrieval.py:_TOKEN_RE` / `_SUB_RE`). Identifiers are split on
`camelCase` / `snake_case` boundaries so "get user profile" matches `getUserProfile`.
Without it, BM25 treats `getUserProfile` as one opaque token and the lexical half goes
blind on exactly the queries it's supposed to win.

**Reciprocal Rank Fusion** (`retrieval.py:search()`, constant `RRF_K`), not score addition.
Dense cosine and BM25 live on different, non-comparable scales; summing them lets whichever
has the wider range dominate. RRF fuses on *rank position* instead, so the two votes are
commensurate and the fusion is stable without per-corpus score normalization.

**Selective cross-encoder rerank** (`retrieval.py:_get_reranker()`, `RERANK_MODEL`,
`RAG_RERANK_AUTO`). A cross-encoder is accurate but slow, so it runs only when it earns its
cost: gated to code-scope queries and triggered by a score threshold/margin
(`RERANK_AUTO_THRESHOLD` / `RERANK_AUTO_MARGIN`). It was *measured* to help code and regress
prose, so it is scoped to where it helps — not applied blindly. If the model isn't present,
retrieval falls back to the fused ranking rather than erroring.

**Language-aware chunking** (`chunkers.py`). `chunk_python()` splits by AST symbol so a chunk
is a whole function/class; `chunk_ts()` / `chunk_shell()` use declaration regexes;
`chunk_fallback()` is a word-count last resort. A chunk that respects symbol boundaries
embeds into a coherent vector; arbitrary fixed-size windows smear two half-functions into one.

**Config by env var** (`config.py`, all `RAG_*`). Zero-setup defaults, every knob overridable,
no config file to thread through — the same reason the eval and CI can pin behavior with
environment variables alone.

## Trust layer (hitgate/)

The retriever is only half the repo; the other half exists to keep its numbers honest:

- `hitgate/run.py` — Hit@K / MRR against a golden set.
- `hitgate/check.sh` — regression gate: re-eval, compare to a frozen baseline within tolerance.
- `hitgate/audit_contamination.py` — flags un-winnable golden cases (answer not in corpus).
- `tests/test_determinism.py` — same query → same top-K ordering, so the numbers are reproducible.

See [DECISIONS.md](./DECISIONS.md) for *why* the system stops where it does, and
[ROADMAP.md](./ROADMAP.md) for measured experiments that might extend it.
