# Domain Context — hitgate

`hitgate` is a **label-free retrieval-quality regression gate** — a pytest-style harness that measures whether a change helped or hurt retrieval ranking, without requiring labeled golden cases or an LLM judge. The harness itself (dependency-free, `python -m hitgate.run`) is the adoptable product; it measures *any* retriever via a simple `--retriever` interface. A bundled hybrid retriever (`ragcore` — dense embeddings + BM25 fused with Reciprocal Rank Fusion) is the reference implementation the harness was built to measure.

## Core Vocabulary

Terms are used precisely as defined here; agents should use these when naming concepts, testing hypotheses, or drafting issues.

**Retriever** — a callable `retrieve(query: str, top: int, scope: str | None) -> Sequence[Mapping]` returning results ranked best-first, each with at least a `path` field. Any retriever: the bundled hybrid, an LLM-reranked BM25, a neural dense-only model, a keyword matcher.

**Harness** — `hitgate/run.py` + supporting tools (`compare.py`, `diff.py`, `check.sh`, `generate.py`, `audit_contamination.py`). Measures a retriever against a golden set, reports Hit@K / MRR, compares two runs, gates on regression (±5pp). Zero third-party dependencies except when measuring the bundled retriever.

**Gate** — a regression threshold enforced by `hitgate/check.sh`. If any metric drops more than 5 percentage points relative to a frozen baseline, the gate exits 1. Gating is the point; the measurements only matter because they enable decisions.

**Baseline** — a frozen snapshot of Hit@K / MRR from a prior run, serialized as JSON with metadata (date, conditions, corpus, retriever model). Baselines are compared to new runs to detect drift.

**Drift** — a change in retrieval quality detected by comparing a new run to a frozen baseline. Drift can be signal (a real improvement or regression from a code change) or noise (the corpus grew, or test case order changed). Honest systems leave both in, label the difference, and let humans decide.

**Scope** — a query-time classification: `code`, `docs`, or `None` (unscoped). Scope gates selective reranking (cross-encoder runs on `code` only; it was measured to help code and regress prose). Some queries are meant for code-aware ranking; others need full-text search. Scope is caller-provided, not inferred.

**Intent** — a category of query type within scope. Not a first-class concept in the harness, but used in ADRs and experimental design to separate "identifier lookup" (exact-token BM25 strength) from "paraphrase questions" (dense embedding strength). Instrumentation for intent is opt-in via golden case annotation.

**Golden set** — a curated collection of (query, expect_path_contains, expect_scope) tuples, serialized as JSONL, representing queries the retriever should be able to answer. Typically 20–100 cases. Generated bootstrapping is available (`hitgate/generate.py`); curation is manual. The golden set is the *specification* of what the retriever should do.

**Hit@K** — binary: did the correct result rank in the top-K? Averaged over all cases in the golden set (e.g., Hit@5 = fraction of 100 cases where the answer was in the top 5). Hit@1 is hardest (exact first hit); Hit@5 is the regression-gated headline (tolerate a little imprecision; focus on "in the top few").

**MRR** (Mean Reciprocal Rank) — average of 1/rank for each case (or 0 if not found). Smoother than Hit@K; rewards a ranker for putting correct results earlier even if it misses the top-K. Reported for awareness; not gated.

**Fused ranking** — hybrid combination of dense (cosine similarity of embeddings) and lexical (BM25) rankings using Reciprocal Rank Fusion (RRF). Each ranker votes by position; votes are summed position-agnostically, so dense and BM25 contributions are commensurate. No per-corpus score normalization needed. The final ranking is both ranker's best ideas, not a bet on one.

**Rerank** (selective, code-scoped) — optional post-processing step: a cross-encoder model re-scores the fused top-K candidates when scope is `code`, bumping high-scoring results forward. If the reranker model is absent, retrieval falls back to the fused ranking without error. Measured to improve code queries; disabled for prose by design.

**Chunk prefix** — an optional enrichment: prepend a chunk's file path and symbol name (for code) or section title (for docs) before the content, so embeddings encode context. Measured to improve dense-ranking quality for small corpora; cost-benefit is corpus-shape-dependent.

## The Two Packages & Their Boundary

**`ragcore/`** — the bundled hybrid retriever.
- **Files:** `build.py` (corpus indexing, AST-aware chunking, embedding), `retrieval.py` (fused ranking, reranking), `chunkers.py` (language-aware chunk boundaries), `config.py` (env var knobs), `query.py` (CLI), `pack.py` (context packing for LLM), `mcp_server.py` (MCP interface).
- **Responsibility:** index code/docs/commits, store embeddings and text in SQLite, search and rank by hybrid logic. One retriever implementation.
- **Dependency shape:** sentence-transformers, numpy, rank-bm25 (declared as `[hybrid]` extra in `pyproject.toml`).
- **Boundary:** `ragcore` is *only* imported inside `hitgate.run:builtin_retriever()` when `--retriever` is not specified. The harness measures it like any other retriever; it is not baked in.

**`hitgate/`** — the eval harness (the adoptable product).
- **Files:** `run.py` (eval main: iterate golden cases, call `--retriever`, compute Hit@K/MRR, write JSON), `compare.py` (diff two runs, highlight deltas), `diff.py` (case-by-case comparison), `check.sh` (bash gate: threshold check, exit 1 on regression), `generate.py` (bootstrap candidates from corpus structure), `audit_contamination.py` (flag un-winnable cases), `plot_history.py` (plot metric trends), `example_external_retriever.py` (reference dumb keyword matcher).
- **Responsibility:** load golden cases, invoke a retriever, tabulate metrics, compare runs, gate on threshold, report findings. Retriever-agnostic.
- **Dependency shape:** dependency-free except for `generate.py`, `audit_contamination.py`, and `test_determinism.py`, which import `ragcore` (only needed when measuring the bundled retriever). `run.py`'s metric math is pure Python.
- **Boundary:** the harness is packaged standalone and importable as `python -m hitgate.run`. To measure your own retriever, pass `--retriever module.path:callable`.

## Key Entry Points & Workflow

**Index (one-time setup for a corpus):**
```bash
RAG_SOURCE_ROOTS="/path/to/your/corpus" python -m ragcore.build
# writes .rag-index/index.sqlite with embedded chunks
```

**Query (interactive or benchmark input):**
```bash
RAG_SOURCE_ROOTS="/path/to/your/corpus" python -m ragcore.query --scope code "how does the reranker fall back"
# outputs ranked [(path, start_line, score), ...]
```

**Eval gate (measure retriever against golden set):**
```bash
python -m hitgate.run \
    --retriever hitgate.example_external_retriever:retrieve \
    --dataset golden.demo.jsonl \
    --label baseline-v1
# writes hitgate/baseline-v1.json with Hit@1/Hit@3/Hit@5/MRR + per-case breakdown
```

**Regression check (gate future runs):**
```bash
bash hitgate/check.sh hitgate/ci.json hitgate/baseline.json
# exits 0 if all metrics within ±5pp of baseline; 1 if any regresses
```

**Drift over self-indexed corpus (demo workflow):**  
The repo's own eval (`hitgate/baseline.json`, 101 golden cases) indexes the repo's source and measures the bundled retriever. Hit@1 and MRR drift as the repo grows (new files can demote borderline cases). Hit@5 is gated at ±5pp and is the headline — drift is expected and honest, not noise to be suppressed.

## Where Decisions & Context Live

- **`DECISIONS.md`** — high-level choices (what was built, what was deliberately *not* built, and the trigger that would reopen each). Read when understanding why the system has its current shape.
- **`docs/adr/`** — architecture decision records, each focused on a specific choice and its rationale. ADR-0001 through ADR-0011 cover triage vocabulary, intent measurement, gating cadence, chunking, reranking calibration, reach strategy, packaging, ecosystem positioning, methodology, model portability, and code-scoped reranking. Read relevant ADRs before working in a specific area.
- **`CHANGELOG.md`** — measured before/after deltas across versions. Honest ablations included (cases where the baseline beats the new approach).
- **`ROADMAP.md`** — candidate experiments (each gated on measured win, none promised). Directions, not commitments.
- **`docs/METHODOLOGY.md`** — full taxonomy of retrieval misses, external corpus benchmarks (7 codebases, zero tuning), and reproduction commands. Read to understand what Hit@1 / Hit@5 mean in context and how corpus module clarity predicts retrieval quality.
- **`ARCHITECTURE.md`** — data flow (index time → query time) and justification for each layer (why hybrid vs single ranker, why RRF, why selective rerank, why language-aware chunking).

## Security & Governance

- `--retriever module:callable` imports and executes arbitrary Python. Use only with modules you trust at the same level as your CI config.
- The project is **not maintained as a service** — a solo operator's personal tool, shared for the methodology. Issues and PRs are welcome but best-effort; no SLA.
- Eval is an **advisory gate** (proves numbers reproduce); not a support guarantee. The harness is stable and dependency-free; the bundled retriever is a reference, not your production component.

## Getting Started (Adopt the Harness)

1. **If measuring your own retriever:** see "Bring your own corpus — 4-step quickstart" in [README.md](./README.md). Write a retriever callable; pass it to `hitgate.run --retriever`; use `check.sh` to gate.
2. **If studying the methodology:** start with [METHODOLOGY.md](./docs/METHODOLOGY.md), then read [DECISIONS.md](./DECISIONS.md) and relevant ADRs.
3. **If extending ragcore:** see [ARCHITECTURE.md](./ARCHITECTURE.md) for layer justifications and [adapters/README.md](./adapters/README.md) for integration patterns.
