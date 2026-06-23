# ADR-0012: Circularity-caveat investment timing — honesty now, mitigation deferred

## Context

The eval is **label-free**: golden queries are mined from or hand-written against the
indexed corpus, so Hit@K measures *retrievability*, not human-judged *relevance*. The
number is optimistic by construction (self-indexed demo Hit@5 ~1.0; the same engine
scores ~0.27 on a hand-labeled set of natural-language code queries). A research+grill
analysis confirmed the caveat is **intrinsic** to label-free eval: the only ways to
*attack* it are (a) escape via an external labeled holdout, (b) harden the queries via
NL naturalization, or (c) calibrate via PPI against a small anchor — and cheap
honesty/exposure that *names* the limit without pretending to fix it. Ten issues were
filed (#44–#53).

The forcing question: **what, if anything, to invest in now** to attack the caveat.
Evidence at decision time: the package is at **t+0** (just published to PyPI, 0 stars,
no Show HN posted, no downloads); the RAG-eval market treats labeled validation as a
**post-MVP maturity feature** (RAGAS/TruLens/DeepEval are label-free at v1); and the
project's standing posture is **validate-not-build** (ADR-0006/0008; `DECISIONS.md` §2
defers ML/labels until ~500 *real* relevance labels accrue).

## Decision

**Defer all caveat-*mitigation* investment; ship only honesty + one cheap launch asset.**

1. **Now (honesty leads the launch):** surface the caveat where users actually read it —
   a `CAVEAT` printed by `run.py` and written into every result JSON (#48), a
   "what it proves vs. doesn't" statement in `README` + `CONTEXT.md` (#52), and the
   selection-bias note surfaced at the external-corpus table (#53). Shipped in PR #54.
2. **Now (one launch asset):** a tiny (~30-query) **hitgate-native** NL labeled anchor on
   a *third-party* repo, published as a `docs/` two-channel honesty number — NOT the
   `--validate-against` product (#44, re-scoped).
3. **Deferred behind demand triggers:** the labeled-validation product (`--validate-against`
   #45, full anchor #44, PPI #47), NL query naturalization (#46), and diagnostics (#49–#51).

## Why deferred

- **No demand signal exists.** t+0, zero traction; investing in mitigation now is a
  demand-blind bet. Honesty is near-free and *advances* the launch; mitigation is
  expensive and speculative.
- **"No labels needed" is the wedge.** Adding a labeled path early signals the synthetic
  number isn't trustworthy alone, eroding the differentiator. The market adds labels
  *after* traction, never at v1.
- **The caveat is intrinsic, not a bug.** No label-free trick narrows the gap; "exposing"
  it with fancier metrics manufactures false confidence. Only external truth escapes it.

## Alternatives considered

**Adopt the labeled-validation product now (#44 full + #45 + #47).** Rejected — most
expensive and brand-tensioning; contraindicated by market norm, zero traction, and
validate-not-build.

**Build NL naturalization now (#46), staying label-free.** Deferred — investment with no
way to validate it helps pre-demand; becomes the *first* label-free mitigation to build
when demand is specifically for harder/realistic queries.

**Defer honesty too (do nothing until traction).** Rejected — honesty is near-free and is
the launch's lead per ADR-0006/0008; a reviewer's "ship honesty after the Show HN"
variant was rejected because it relitigates the settled honesty-first positioning.

## Consequences

- The caveat is **exposed and documented**, not mitigated. A future agent picking up
  #45/#46/#47 must read this ADR first to understand *why* the labeled path is deferred.
- `run.py` output and result JSON now carry a `caveat` field — consumers read by key, so
  the addition is backward-compatible.
- The labeled-validation product is not pre-built; if suddenly demanded, it is additive
  (an optional `--validate-against` flag; the label-free default path is untouched).

## Revisit when

**Flip to building the labeled path (#45 + grow #44 + #47) when ANY of:**

1. **Demand** — ≥1 credible external (non-owner) "I ran it on my own retriever" report
   within 48h of a Show HN (the launch success bar; ADR-0008).
2. **Request** — ≥1 external-human GitHub issue/discussion requesting labeled validation
   or disputing the synthetic number.
3. **Adoption** — ≥25 external GitHub stars **or** sustained ≥50 PyPI downloads/month for
   two consecutive months.

Build NL naturalization (#46) first among mitigations if demand is specifically for
harder/more-realistic queries. The honesty items (#48/#52/#53) + the launch anchor (#44)
ship now regardless. If no Show HN posts within 30 days, reopen this ADR — the posture
assumes the launch is imminent. See `DECISIONS.md` §2 for the broader ~500-real-label
ML/labels deferral this refines.
