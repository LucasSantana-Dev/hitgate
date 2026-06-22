# ADR-0010: Reranker model — portability vs. quality tradeoff

## Context

The next decision after establishing the reranking strategy is which cross-encoder reranker model
to use by default. The tradeoff is between model size/latency (portability) and ranking quality
(effectiveness).

Two candidates were measured on the **50-case golden set** (hybrid mode, forced global reranking,
Apple M1 CPU):

1. **ms-marco-MiniLM-L-6-v2** — 88MB, small, fast
2. **BAAI/bge-reranker-v2-m3** — 2.1GB, large, slower but stronger

## Measured results (50-case golden set, forced reranking, ROADMAP §5)

| Model | Size | Pipeline time | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---|---|---|---|
| *(no rerank)* | — | 15.5 s | 0.56 | 0.90 | 1.0 | 0.741 |
| `ms-marco-MiniLM-L-6-v2` | 88 MB | 30.2 s | **0.62** | **0.86** | **0.96** | **0.746** |
| `BAAI/bge-reranker-v2-m3` | 2.1 GB | 194.2 s | **0.82** | **0.94** | **0.96** | **0.875** |

**Critical finding (from ROADMAP §5):** Forced global reranking with *both* models regresses Hit@5
from 1.0 → 0.96 (2 of 50 cases demoted past rank 5). This regression affects both code and
non-code scopes uniformly. The auto-calibrated trigger (`RAG_RERANK_AUTO_MARGIN=0.015`) avoids
this by firing selectively on genuinely ambiguous queries only.

## Decision

**Default reranker: `cross-encoder/ms-marco-MiniLM-L-6-v2` for portability.**
**Optional upgrade: `BAAI/bge-reranker-v2-m3` via `RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3`
when disk space and latency are acceptable.**

### Rationale

The bge-reranker-v2-m3 model is **strictly better** on measured quality:
- Hit@1 improvement: 0.56→0.82 (+26pp absolute, +46% relative)
- MRR improvement: 0.741→0.875 (+13.4pp absolute, +18% relative)
- No regression on non-code scopes (Hit@5 stays at 0.96 for both models)
- Latency cost: 194.2s vs 30.2s for 50 queries (+164.0s total, ~3.28s per query)

However, **portability is a non-negotiable property of a reusable tool:**
- The default reranker model must work on any machine with ~200MB free disk (model + dependencies).
- 2.1GB is a material barrier for local/edge deployment, CI runners, and resource-constrained environments.
- The codebase should not *require* users to download a 2.1GB model; they should be able to run
  the full harness with just the core dependencies.

**Solution:** Ship ms-marco as the default (`RERANK_MODEL_DEFAULT`), then make bge-reranker-v2-m3
**opt-in via environment variable** (`RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3`). This preserves
portability for the majority case while enabling users to trade disk/latency for quality when they have
the budget.

## Consequences

- `RERANK_MODEL_DEFAULT = "cross-encoder/ms-marco-MiniLM-L-6-v2"` in `ragcore/retrieval.py` (line 45).
- When users want the quality upgrade, they override: `RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3`.
- The eval gate (`eval/check.sh`) uses the default (ms-marco) for reproducibility on any machine.
- Users operating with selective code-scope reranking (ADR-0011) can combine this choice with
  the selective trigger for measured gains on the narrower scope (code queries).
- Graceful fallback (ADR-0011) ensures that if the model is unavailable or fails to load, queries
  still complete on the fused ranking.

## Revisit when

- A third reranker model becomes available with better portability/quality ratio (e.g., <500MB,
  Hit@1>0.70 on the 50-case set) — benchmark and consider re-defaulting.
- Real usage telemetry shows that the majority of users set `RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3`
  — at that point consider flipping the default (requires documenting the 2.1GB disk requirement
  more prominently and updating CI/packaging).
- A machine-learning community release (e.g., a code-specialized reranker) improves on bge-v2-m3 —
  benchmark it against the current table and update this decision.

## Related

- ADR-0005: Auto-rerank trigger calibration (separate, governs when to rerank vs. not)
- ADR-0011: Selective code-scope reranking (complements this choice for scope-specific strategies)
- ROADMAP §5: Reranker Pareto table and measurement methodology
- `ragcore/retrieval.py`: Model initialization (line 45)
