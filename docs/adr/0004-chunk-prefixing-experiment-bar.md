# ADR-0004: Chunk prefixing experiment bar

## Context

Roadmap item #2 proposes prepending a short context line (file path, symbol role) to
each chunk before embedding, to address vocabulary mismatch between natural-language
queries and code identifiers. The original bar was "measurably improves code-scope
Hit@5 without regressing prose."

After the chunker fix (ADR-0001 / `fix(chunker)`), Hit@5 is 1.0 across all three
non-rerank modes. The original bar cannot be met — the metric has saturated on the
current golden set.

Post-chunker-fix baselines (hybrid mode, 12-case set):

| Metric | Value |
|--------|-------|
| Hit@5  | 1.000 |
| Hit@1  | 0.667 |
| MRR    | 0.833 |

Hit@1 and MRR are live signals. The question is whether chunk prefixing can move them
on the *current* 12-case set, or whether the current set is too BM25-friendly to detect
a semantic embedding improvement at all.

## Decision

**Two-stage approach:**

**Stage 1 — Pilot on current set.** Implement chunk prefixing and measure Hit@1/MRR on
the existing 12-case golden set. The bar:

> Improves hybrid MRR by ≥+0.05 (i.e., ≥0.883) with no intent class regressing by >5pp.

If Stage 1 returns a positive result, ship — paraphrase cases are not a prerequisite.

**Stage 2 — Add paraphrase cases (if Stage 1 is null).** If Stage 1 returns no
improvement, the null result is expected (12 identifier-match cases are BM25-friendly;
chunk prefixing's semantic boost has nothing to win on). Add 3–5 paraphrase golden
cases — queries with no shared tokens with the implementation — and re-run Stage 1 on
the expanded set. Paraphrase cases are exactly where chunk prefixing should help.

## Why not paraphrase cases first

Writing paraphrase cases before the pilot is premature: if chunk prefixing improves
MRR on the current set (even on identifier-match queries, via disambiguation), the
feature is validated without expanding the golden set. Paraphrase cases as a
prerequisite would impose unnecessary cost.

## Why not ship with the original Hit@5 bar

Hit@5=1.0 is a ceiling artifact of the current 12-case set, not proof that chunk
prefixing has no effect. Retreating to a null result on the *wrong instrument* and
calling it "chunk prefixing doesn't help" would be a measurement error.

## Consequences

- The chunk prefixing implementation can proceed immediately.
- A null Stage 1 result is informative but not final — it triggers Stage 2, not
  rejection.
- "Measurable improvement" is defined as ≥+0.05 MRR on hybrid, no class regressing
  by >5pp. This is consistent with the existing eval/check.sh ±5pp gate.
- If both stages return null results, chunk prefixing is deferred with the finding
  recorded.

## Revisit when

- Real usage telemetry shows a pattern of paraphrase-style queries (natural-language,
  no shared tokens with code) — at that point Stage 2 becomes urgent regardless of
  Stage 1 outcome.
- The golden set grows past ~50 cases — at that scale Hit@1 variance drops enough
  that smaller MRR improvements become detectable and the bar can tighten.

---

## Stage 1 result (run on 2026-06-19)

Ablation: full rebuild WITH prefix (`RAG_CHUNK_CONTEXT_PREFIX=on`, default) vs WITHOUT
(`RAG_CHUNK_CONTEXT_PREFIX=off`), hybrid mode, `RAG_RERANK_AUTO=off`, 12-case golden set.

| Mode | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---|---|
| WITH context prefix (default) | 0.583 | 1.0 | 1.0 | 0.778 |
| WITHOUT context prefix | 0.583 | 1.0 | 1.0 | 0.778 |
| **Delta** | **0.0** | **0.0** | **0.0** | **0.0** |

**Result: null.** No measurable difference on the current 12-case golden set. This
is the expected outcome: all 12 cases are identifier/keyword lookups where BM25 dominates;
the dense channel's context prefix has no retrieval surface to win on because the
queries already share tokens with the implementation.

**Trigger for Stage 2:** null Stage 1 result triggers the addition of 3–5 paraphrase
golden cases — queries with no shared tokens with the implementation. This is where
chunk prefixing's semantic boost should materialize.

**Corpus note:** the baseline also drifted during this session (MRR 0.833→0.778,
Hit@1 0.667→0.583) due to corpus growth (new docs/adr/ and docs/agents/ files added
competing chunks). Hit@5 held at 1.0. Baseline re-frozen at the new values; the
drift is expected living-corpus behavior, not a code regression.
