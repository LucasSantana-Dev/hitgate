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

## 1. Comparative benchmark vs. named baselines

Today the demo reports a single number (Hit@5 1.0, self-indexed after the chunker fix
that added module-level constant indexing). A single number tells you the system works;
it doesn't tell you the hybrid+RRF design is *earning its complexity*. The experiment:
run the same reproducible demo eval against

- **BM25 only** (drop the dense half),
- a **late-interaction / token-level** retriever (e.g. a ColBERT-style scorer),
- an **off-the-shelf framework's default** RAG pipeline,

and publish the honest delta — including any scope where the simpler baseline wins.

**Bar to ship:** the comparison is the deliverable; it ships regardless of outcome. If
BM25-only ties the hybrid on this corpus, that finding is *more* valuable than a number
that flatters the design.

## 2. Contextual chunk prefixing ✅ shipped (marginal positive result)

Code retrieval's hardest failure is vocabulary mismatch: a natural-language query shares
almost no tokens with an implementation. The fix: prepend `source_type | repo | filename | symbol`
to each chunk before embedding, so the dense channel sees the context the raw lines omit.

**Experiment:** Two-stage ablation. Stage 1 (12-case identifier-only set) returned a null result —
expected, because BM25 dominates identifier lookups. Stage 2 expanded the golden set to 17 cases
with 5 paraphrase queries (no shared tokens with implementation). WITH vs WITHOUT prefix on the
17-case set: **+0.050 MRR / +0.059 Hit@1**, no class regression. Bar met.

Key finding: the gain is driven by one query ("folder names that get skipped") jumping rank 5→1
when the prefix adds "config.py" as a semantic hint. The chunkers.py paraphrase case remains a
persistent miss in both modes — a harder vocabulary gap ("passages", "vectorized") where even the
filename doesn't help. The golden set now has 17 cases (5 paraphrase). See `docs/adr/0004`.

**Honest caveat:** n=5 paraphrase cases means ±1 case is ±0.02 MRR. The result is directionally
correct but statistically thin. The feature ships default-on at zero runtime cost (prefix not
stored); the stronger validation would require ≥20 paraphrase cases.

## 3. Run the eval as tracked experiments (measurement, not model)

The harness currently compares runs by diffing JSON files. An **opt-in adapter** could
push the eval set and its Hit@K/MRR scores into an experiment-tracking tool (e.g.
[Langfuse](https://langfuse.com) Datasets/Experiments), so before/after comparisons are
versioned and drillable instead of hand-diffed.

This is squarely on-thesis — *improve the measurement, not the model.* Scope is
**eval-first**: tracking offline eval campaigns, not instrumenting live queries. Stays
an adapter, never a core dependency, in keeping with [What this is NOT](./README.md).

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

## 5. Reranker tradeoff table

The optional cross-encoder reranker is one specific model today. A small **Pareto study**
across a few rerankers — quality vs. latency vs. memory footprint — would let a forker
pick one for their resource budget, instead of inheriting one tuned for a 16 GB laptop.

**Bar to ship:** a reproducible comparison table; the default only changes if a
candidate is strictly better on the demo within a stated latency budget.

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
