# Open directions — candidate experiments, not commitments

This is **not** a product roadmap. It's a list of directions that could improve the
retriever or the harness, written down so the reasoning is visible. Consistent with the
rest of this repo, none of them ship on enthusiasm: each is gated on a **measured
before/after** on the reproducible demo corpus, and each names the bar it has to clear
to earn a place in the core. Most will probably stay candidates — that's the point.

The discipline is the same one in [DECISIONS.md](./DECISIONS.md): *measure → challenge →
decide → record the trigger that would reopen it.* These are the "challenge" stage, in
public.

---

## 1. Comparative benchmark vs. named baselines ✅ shipped (BM25 vs dense vs hybrid)

The comparison shipped with the paraphrase golden-set expansion (ROADMAP #2 Stage 2).
The BM25 vs dense vs hybrid ablation on the 17-case set is in `docs/METHODOLOGY.md`.
Key finding: **hybrid earned its complexity once the golden set included paraphrase queries.**
On identifier-only queries, BM25-only dominated (Hit@1=0.917, MRR=0.958); on the expanded
17-case set, hybrid achieves Hit@5=0.941 vs BM25's 0.882, and is the only mode to
achieve Hit@5=1.0 on both retrieval and infrastructure intent classes simultaneously.

**Deferred:** late-interaction (ColBERT-style) and off-the-shelf framework comparison.
Reopen trigger: a use case arises where sub-word token overlap is the primary failure mode
and BM25/dense fusion hasn't already addressed it on a ≥30-case eval set.

## 2. Contextual chunk prefixing ✅ shipped (precision-positive, coverage-neutral)

Code retrieval's hardest failure is vocabulary mismatch: a natural-language query shares
almost no tokens with an implementation. The fix: prepend `source_type | repo | filename | symbol`
to each chunk before embedding, so the dense channel sees the context the raw lines omit.

**Three-stage experiment:**

- **Stage 1** (12-case identifier set): null result — expected, BM25 dominates identifier lookups.
- **Stage 2** (17 cases, +5 paraphrase): +0.050 MRR / +0.059 Hit@1, 0.0 Hit@5 delta. Positive.
- **Stage 3** (23 cases, +11 paraphrase): +0.017 MRR / +0.044 Hit@1, **−0.044 Hit@5**. Mixed.

The refined finding: prefix is a *precision optimizer*. It boosts Hit@1 and MRR on cases where
the filename is a semantic anchor (config.py for "folder names", retrieval.py for "auto rerank"),
but can hurt Hit@5 where prefix tokens attract false positives (chunkers.py second angle drops
from rank 5 to MISS — `build.py` outscores it on "source code fragments" after the prefix
amplifies the overlap). The reranker recovers the chunkers.py miss (rank 6→1 with cross-encoder).

The golden set now has **23 cases (11 paraphrase)**. See `docs/adr/0004` for the full record.

**Decision stands: default-on.** Cost is zero; MRR direction remains positive; the one
reproducible Hit@5 regression is compensated by the gated reranker.

## 3. Run the eval as tracked experiments (measurement, not model) ✅ shipped

The harness currently compares runs by diffing JSON files. An **opt-in adapter** pushes
the eval set and its Hit@K/MRR scores into [Langfuse](https://langfuse.com)
Datasets/Experiments, so before/after comparisons are versioned and drillable instead
of hand-diffed.

Shipped as `adapters/langfuse_eval.py`. Scores recorded per item: `hit@1`, `hit@3`,
`hit@5`, `mrr_contribution`, `hit_rank`. Dataset items are stable-ID'd so every
experiment run accumulates against the same dataset. Usage:

```bash
pip install langfuse
python adapters/langfuse_eval.py \
    --dataset eval/golden.demo.jsonl \
    --results  eval/my-run.json \
    --run-name "feat/my-experiment"
```

Stays an adapter, never a core dependency, in keeping with [What this is NOT](./README.md).

## 4. Stratified (per-intent) measurement ✅ shipped

~~The aggregate Hit@K hides *where* the system is weak.~~ Done. The eval harness now
reports `by_intent` breakdowns across three classes — `retrieval` (n=21), `indexing`
(n=15), `infrastructure` (n=23) — alongside the existing `by_scope` rows. Cases without
an `intent` field fall into `unclassified` for backward compatibility. Per-intent CI
gating is **active** (ADR-0003 resolved 2026-06-19); all three classes hold Hit@5=1.0
at n≥15, making the ±5pp tolerance meaningful.

Bonus: stratified measurement immediately exposed a chunker gap — module-level Python
constants and docstrings were silently dropped, causing two `infrastructure` cases to
miss outside top-10. Fixed in the same session; Hit@5 moved from 0.833 → 1.0.

## 5. Reranker tradeoff table + auto-trigger calibration ✅ shipped

Two models measured on the **50-case golden set** (hybrid mode, CPU Apple M1, forced reranking; the set has since grown to 59 cases — see item #6):

| Model | Size | Pipeline time¹ | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---|---|---|---|
| *(no rerank)* | — | 15.5 s | 0.56 | 0.90 | **1.0** | 0.741 |
| `ms-marco-MiniLM-L-6-v2` *(default)* | 88 MB | 30.2 s | 0.62 | 0.86 | 0.96 | 0.746 |
| `BAAI/bge-reranker-v2-m3` | 2.1 GB | 194.2 s | **0.82** | **0.94** | 0.96 | **0.875** |

¹ End-to-end for 50 queries (embed + retrieve + rerank).

**Critical finding:** forced global reranking drops Hit@5 from 1.0 → 0.96 for *both* models
— 2 of 50 cases ranked 3–5 by hybrid fusion get demoted past rank 5 by the cross-encoder.
Calibrated auto-trigger (`RAG_RERANK_AUTO_MARGIN=0.015`) avoids this: fires only on
genuinely ambiguous queries, maintaining Hit@5=1.0 while gaining Hit@1=0.62 (+6pp) and
MRR=0.763 (+2.2pp) vs no-rerank baseline.

Default stays `ms-marco-MiniLM-L-6-v2` for portability (88 MB); set
`RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3` when footprint is not a constraint. Full
table, calibration sweep, and miss taxonomy in `docs/METHODOLOGY.md` and `docs/adr/0005`.

## 6. Expand golden set to ~100 cases with LLM-generated paraphrases

**Status: candidate.** The 59-case set is saturated at Hit@5=1.0 — adding new cases that
also hit at rank 1–5 proves nothing. The set needs to grow to the point where a retrieval
change can *discriminate* meaningfully across cases, not just hold a ceiling.

The generator's `--llm` path (ADR-0002 plumbing, no extra dep) can produce an
`identifier + paraphrase` pair per chunk via any OpenAI-compatible API. A 100-case set
with ~50 paraphrases distributed evenly across intent classes would give each class
enough sample variance for a 5pp gate swing to signal a real regression, not noise.

**Gate to ship:** a 100-case run where at least one plausible retrieval change (e.g.
embedding model swap, BM25 weight change) moves Hit@5 by a detectable and reproducible
5pp in the expected direction. If the set is still too easy to discriminate, it doesn't
earn a place in the core.

**Reopen trigger:** a retrieval change passes the aggregate Hit@5 gate but a
per-intent class visibly degrades in local runs — meaning the 59-case set missed it.

---

## Deliberately *not* on this list

To save anyone the suggestion — these were considered and declined, with reasons in
[DECISIONS.md](./DECISIONS.md):

- **Training a learned ranker / fine-tuning embeddings** — a curated eval is ~100 cases;
  learned ranking wants orders of magnitude more *real* labels. Reopen trigger is
  recorded in DECISIONS.md, and it isn't met.
- **Graph-aware retrieval / vendor-coupled sources** — removed from the core on purpose
  to keep it a portable superset that indexes any tree with three dependencies.
- **A plugin framework, hosted service, or examples gallery** — this is published for
  the methodology, not as a product; growth in surface area is a cost, not a goal.

Each item here ships only if a measurement says it should, and gets recorded in
DECISIONS.md with the condition that would reopen it. Until then they're exactly what
this file says they are: candidates.
