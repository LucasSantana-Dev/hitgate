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
reports `by_intent` breakdowns across three classes — `retrieval` (n=5), `indexing`
(n=4), `infrastructure` (n=3) — alongside the existing `by_scope` rows. Cases without
an `intent` field fall into `unclassified` for backward compatibility. Per-intent CI
gating is deliberately deferred until classes are large enough for a 5pp tolerance to
be meaningful (see `docs/adr/0002` and `docs/adr/0003`).

Bonus: stratified measurement immediately exposed a chunker gap — module-level Python
constants and docstrings were silently dropped, causing two `infrastructure` cases to
miss outside top-10. Fixed in the same session; Hit@5 moved from 0.833 → 1.0.

## 5. Reranker tradeoff table ✅ shipped

Two models measured on the 17-case golden set (hybrid mode, CPU):

| Model | Size | Warm latency | Hit@1 | MRR | Infra Hit@5 |
|---|---|---|---|---|---|
| `ms-marco-MiniLM-L-6-v2` *(default)* | 88 MB | 48 ms | 0.529 | 0.696 | 0.75 |
| `BAAI/bge-reranker-v2-m3` | 2.1 GB | 88 ms | **0.647** | **0.767** | **1.0** |

`bge-reranker-v2-m3` is strictly better on quality (no metric regresses). Default stays
`ms-marco-L-6-v2` for portability (88MB); the bar for switching is met — set
`RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3` when footprint is not a constraint. Full
table and analysis in `docs/METHODOLOGY.md`.

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
