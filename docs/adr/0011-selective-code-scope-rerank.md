# ADR-0011: Selective code-scope reranking

## Context

After validating the baseline hybrid retriever (BM25 + dense + RRF) across a 50-case golden set,
code-scope queries emerged as a measurable weak point. The hybrid fused ranking often ranks the
correct code chunk outside the top 5 for certain code-seeking queries.

The obvious move would be to apply reranking globally (all scopes). However, the critical finding
from ROADMAP §5 is that **forced global reranking regresses Hit@5 from 1.0 → 0.96 for both
models** — demoting 2 of 50 cases past rank 5 across all scope types. This uniform regression
suggests the cross-encoder is tuned for code similarity and degrades on non-code prose.

The question: can reranking be scoped to code queries only, recovering code performance without
regressing other scopes?

## Decision

**Apply cross-encoder reranking selectively to code-scope queries only (`RAG_CODE_RERANK`, default OFF).**

The selective operating point was validated during development (2026-06-15) and avoids the
measured Hit@5 regression of forced-global reranking. Non-code scopes remain on fused ranking,
capturing the gains on code without regressions elsewhere.

Rationale:
- **Forced-global regresses Hit@5 uniformly:** Both ms-marco and bge drop Hit@5 1.0→0.96 when
  applied to all scopes (ROADMAP §5).
- **Code is the weak spot for fused ranking:** Selective reranking recovers it where needed.
- **Graceful fallback:** If the reranker is unavailable or fails, queries complete on fused
  ranking with no data loss (stderr warning logged).

## Baseline (50-case golden set, no reranking, hybrid mode, ROADMAP §5)

Aggregate: Hit@1=0.56, Hit@5=1.0, MRR=0.741

Code is the measured weak point for hybrid fused ranking; selective reranking on code scope
only avoids the Hit@5 regression observed with forced-global reranking.

## Key constraint: the exact selective-scope deltas are NOT in committed artifacts

Earlier work derived specific deltas (e.g., "+4.9pp code / +2.1pp overall") from inline validation
during development, but these measurements were never committed to a reproducible ablation file.
The **validated finding** is qualitative: selective code-scope reranking captures gains where
fused ranking is weakest (code) while avoiding the Hit@5 regression observed with forced-global
reranking.

**Reopen trigger: commit a standalone selective code-scope ablation to quantify the exact delta.**
This ADR documents the *strategy* (selective, not global) and *rationale* (avoid regression); the
exact *numbers* require a proper ablation commit alongside the implementation.

## Implementation

- `RAG_CODE_RERANK` environment variable (default `off`) controls whether code-scope
  reranking is enabled.
- When `RAG_CODE_RERANK=on`, queries with `scope_types` containing "code" trigger the reranker;
  all other scope types use the fused ranking.
- `RAG_RERANK_MODEL` selects the reranker model; bge-reranker-v2-m3 is the validated choice
  (see ADR-0010). Using a different model with `RAG_CODE_RERANK=on` is unsupported.
- The fallback path is transparent: if the reranker fails, stderr logs a warning and the
  query completes on fused ranking. No exceptions leak to the caller (line 288–292 in `retrieval.py`).

## Why not forced global reranking

From ROADMAP §5 (50-case measurement, hybrid mode, forced reranking with both models):

| Model | Hit@1 | Hit@5 (no rerank) | Hit@5 (forced) | Notes |
|-------|-------|---------|---------|---------|
| ms-marco | 0.62 | 1.0 | 0.96 | Regression: 2 cases demoted past rank 5 |
| bge-v2-m3 | 0.82 | 1.0 | 0.96 | Regression: 2 cases demoted past rank 5 |

The regression is uniform across scope types, indicating the cross-encoder prioritizes code-like
signals. Selective confinement to code scope preserves the Hit@5=1.0 floor where fused ranking is
strong (infrastructure, indexing) while allowing code to benefit where it's weak.

## Consequences

- The eval gate (`eval/check.sh`) measures the **no-rerank baseline** for reproducibility
  (no reranker model required to validate the gated Hit@5 number).
- Code-scope queries have an optional path through the cross-encoder; non-code queries never
  hit it, preserving baseline performance.
- The strategy integrates with ADR-0010's model choice: selective code-scope triggers only when
  explicitly enabled; the default is fused ranking for portability.

## Revisit when

- A user reports the selective reranking firing unexpectedly on non-code scopes — refine the
  `is_code_scope` heuristic in `retrieval.py:259`.
- The golden set grows past ~200 cases and stratified per-intent measurement shows a code-intent
  class visibly degrade in local runs — indicating the 50-case set missed a failure mode.
- Disk space or latency constraints shift materially (e.g., better models emerge, faster hardware,
  cloud inference available) — re-measure the selective-code tradeoff against the new frontier.
- A user reports strong demand for code-scope reranking (high Hit@1 gain on live code queries)
  — at that point consider making `RAG_CODE_RERANK=on` the default and documenting the model
  requirement more prominently.

## Related

- ADR-0010: Reranker model choice (bge-v2-m3 vs ms-marco; this ADR governs WHEN, 0010 governs WHICH)
- ADR-0005: Auto-rerank trigger calibration (separate strategy for ambiguity-based selective triggering)
- ROADMAP §5: Reranker Pareto table and forced-global regression finding
- `ragcore/retrieval.py` (lines 259, 273–275): Scope detection and selective trigger
