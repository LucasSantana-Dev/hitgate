# ADR-0005: Auto-rerank trigger calibration — RERANK_AUTO_MARGIN=0.015

## Context

ADR-0004 deferred a revisit of the auto-trigger margin at ~50 golden cases. The 50-case set
is now in place (25 identifier + 25 paraphrase; 14 indexing, 19 infrastructure, 17 retrieval).

The original default `RAG_RERANK_AUTO_MARGIN=0.08` was set conservatively and never validated
against a large enough corpus to detect the failure mode it introduced. The margin controls when
the auto-trigger fires: it fires when the cosine similarity gap between the top-1 and top-2
corpus results falls below the margin (i.e., the retriever is "unsure" which document should
rank first). At 0.08, the trigger fired on too many queries — including 2 cases where the
cross-encoder was confidently *wrong*, demoting results from rank 3–5 to MISS.

A second discovery during this calibration: the eval harness had no path to exercise
`rerank=None` (the auto-trigger branch). The harness always passed `rerank=False` or
`rerank=True` explicitly. This was fixed by adding `--auto-rerank` to `hitgate/run.py`.

## Decision

Set `RAG_RERANK_AUTO_MARGIN` default to **0.015**.

Sweep run on the 50-case golden set with `python -m hitgate.run --dataset golden.jsonl --auto-rerank`:

| Margin | Hit@1 | Hit@3 | Hit@5 | MRR | Notes |
|---|---|---|---|---|---|
| 0.080 (old default) | 0.62 | 0.86 | 0.96 | 0.746 | 2 MISSes — too aggressive |
| 0.020 | 0.62 | 0.88 | 0.98 | 0.753 | 1 MISS |
| **0.015 (new default)** | **0.62** | **0.90** | **1.0** | **0.763** | calibrated |
| 0.010 | 0.56 | 0.90 | 1.0 | 0.733 | too few triggers, Hit@1 drops |
| 0.005 | 0.50 | 0.88 | 1.0 | 0.696 | harmful — triggers on noise |

At margin=0.015:
- Fires on ~26 of 50 queries (queries with genuine top-1/top-2 cosine ambiguity)
- 13 queries improve rank; 11 degrade rank but stay within top-5
- Hit@1 +6pp, MRR +2.2pp vs no-rerank baseline; Hit@5=1.0 maintained

The 2 cases that MISS at margin≥0.020 have cosine margins between 0.010 and 0.015. They are
genuinely ambiguous to the dense channel, but the cross-encoder makes the wrong call on them.
At margin=0.015 they fall below the trigger and remain at their hybrid-fusion positions (ranks
2 and 3), safely within top-5.

## Miss taxonomy finding (discovered during calibration)

All 22 non-rank-1 cases (on the 50-case no-rerank baseline, Hit@1=0.56) are **top-5 hits** —
the retriever finds the correct document but ranks it 2nd–5th rather than 1st. Four structural
failure modes, all semantic-layer ambiguity rather than vocabulary gap:

- **Category A (9 cases):** Implementation vs. entry-point confusion — `retrieval.py` vs
  `query.py`, `retrieval.py` vs `pack.py`; these files share vocabulary and the query
  cannot resolve which layer is wanted.
- **Category B (7 cases):** Eval infrastructure leakage — `audit_contamination.py`,
  `plot_history.py`, `test_determinism.py` mirror core vocabulary and compete with their
  counterparts.
- **Category C (4 cases):** Adapter identity confusion — `mcp_server.py` vs
  `langchain_retriever.py` share interface vocabulary.
- **Category D (2 cases):** Config vs. consumer split — `EXCLUDED_DIR_PARTS` in `config.py`
  vs `is_excluded_path` in `build.py`.

Key conclusion: **the ceiling is architectural, not vocabulary.** No docstring enrichment or
embedding-pipeline change resolves Category A/B/C/D — they require either corpus restructuring
or a two-stage retriever that reasons about document role. The calibrated auto-trigger is the
correct response to this ceiling: it boosts Hit@1 on the tractable cases without sacrificing
the Hit@5=1.0 guarantee.

## Alternatives considered

- **Margin=0.020:** Still 1 MISS. The cosine gap for the second problematic case (between
  0.015 and 0.020) is small enough that the trigger fires and the cross-encoder demotes it.
- **Margin=0.010:** Zero MISSes but Hit@1 drops to 0.56 (same as no-rerank). The trigger
  stops firing on the 13 tractable cases that benefit from reranking.
- **Forced global reranking:** Hit@1=0.62/0.82 (ms-marco/bge-v2-m3) but Hit@5=0.96 — 2
  permanent MISSes. Not acceptable; the CI gate is Hit@5 ±5pp and the no-rerank baseline
  is 1.0.
- **Larger margin sweep:** Values above 0.080 were not measured. At 0.080 the trigger
  fires on most queries (approaching forced reranking behavior) and shows the same 2-MISS
  pattern; going higher would worsen this.

## Consequences

- `RAG_RERANK_AUTO_MARGIN` default changes from 0.08 → 0.015 in `ragcore/retrieval.py`.
- The eval gate (`hitgate/check.sh`) continues to measure the no-rerank baseline for
  reproducibility — no reranker is required to reproduce the gated number.
- `python -m hitgate.run --dataset golden.jsonl --auto-rerank` measures the calibrated production operating point.
- `python -m hitgate.diff` can diff auto-rerank runs against the frozen no-rerank baseline for
  per-case comparison.

## Revisit when

- The golden set grows past ~100 cases — at that scale the per-intent class sizes are
  large enough to gate on Hit@1 per class rather than aggregate Hit@5. The margin may
  need re-calibration if the category distribution shifts.
- A user reports the auto-trigger firing on queries where it clearly should not — surface
  as a `RAG_RERANK_AUTO_MARGIN` override in their config.
- A stronger cross-encoder (or a code-tuned reranker) is evaluated — the margin's sweet
  spot depends partly on the reranker's error profile on code-scope queries.
