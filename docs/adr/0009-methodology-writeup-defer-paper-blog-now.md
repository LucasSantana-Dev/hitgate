# ADR-0009: Methodology writeup — defer the formal paper, ship an honest blog now, JOSS when adoption + maturity arrive

## Status

Accepted (2026-06-21). Decided via `research-and-decide`: 3-agent research (venue mechanics /
citation precedent / defensible-thesis) → `decision-critic` (ENDORSE-WITH-CHANGES) → orchestrator
verification of the hard gates → this record. **Refines the "arXiv methodology note" lever named in
[ADR-0006](0006-reach-strategy-retrieval-gate-positioning.md) and [ADR-0008](0008-ecosystem-embedding-credibility-first.md)**:
the formal note is retargeted (arXiv → JOSS), deferred, and gated.

## Context

ADR-0006's reference+usage strategy named a formal methodology note (the RAGAS legitimacy-backfill
pattern) as a durable lever. This decides whether/where/when to write it. hitgate is a **solo,
unfunded, non-academic** maintainer's harness, **~5 days public, 0 stars, not yet on PyPI, zero
external adopters.** Research surfaced a clear, somewhat deflating picture:

**Venue mechanics.**
- **arXiv cs.IR**: as of Jan 2026 a **hard endorsement gate** — a first-time unaffiliated submitter
  needs an established cs.IR researcher to personally vouch (anti-AI-slop). No revision path. Poor
  solo fit.
- **JOSS** (Journal of Open Source Software): the best *citable* fit — real Crossref DOI,
  solo/non-academic friendly, open GitHub peer review. **But two hard gates: (1) "clear research
  impact" / external adoption or a published benchmark using it; (2) 6+ months public dev history.**
- **Workshop** (Eval4RAG/ECIR): peer-reviewed, medium durability, CFP-timing-gated.
- **Blog** (own + Medium/dev.to): zero citation value, ~90-day decay, but cheap, immediate, and
  contrarian-honest posts travel 2–4× a plain launch.

**Precedent (decisive).** **DeepEval** — a widely-adopted *solo* tool with no paper — has ~zero
academic citations: adoption without a citable paper does not yield citations. Solo non-academic
notes don't reliably get cited (≈29% of JOSS papers get 0 citations; a 20–40% solo-author penalty);
the cited exceptions had prior reputation or institutional backing. For a solo tool, the paper should
**follow** adoption, not precede it.

**Thesis (honest, repo-grounded).** The strongest defensible claim — "label-free retrieval-ranking
regression gating on your own corpus, honest miss taxonomy, frozen baseline + per-intent CI gates" —
is **blog-grade, not arXiv/JOSS contribution**: RRF+dense+BM25 is consensus, IR regression-testing
dates to the 1990s, the per-intent gate is competent engineering, "BM25>hybrid / radical honesty" is
now-consensus narrative, and the 70-repo breadth claim is undercut by Hit@5 saturation on
auto-generated queries, self-index bias, no human-labeled gold, and single-author scope.

**Verified gates (orchestrator).** First commit **2026-06-16 (~5 days of public history)** vs JOSS's
6-month requirement; **0 stars / 0 forks** vs JOSS's research-impact gate. Both JOSS gates hard-fail
now; arXiv is endorsement-walled. **A formal paper is currently impossible *and* low-yield** — and no
reframing of the contribution can clear a maturity/endorsement gate.

## Decision

Treat this as three separable bets (venue / timing / effort), not one:

1. **Timing — DEFER the formal paper.** A solo, pre-adoption, thin-novelty paper now ≈ 0 citations
   (DeepEval counter-case), and both formal venues are blocked anyway (verified). No formal-paper
   effort is spent until the gate below trips.
2. **Effort (now) — ship an honest methodology BLOG POST**, scoped to *"here's how to gate retrieval
   honestly without labels"* — **no research-contribution overclaim**, and it **discloses the
   weaknesses** (Hit@5 saturation on auto-queries, self-index bias, single-author corpus). It is
   ADR-0006's "opportunistic methodology post," and it must be **sequenced with the launch**
   (Show HN / Awesome PR / PyPI) for visibility — a standalone post that nothing points at just
   decays. The blog's job is awareness + driving the adoption that unlocks the formal venue, **not**
   citation.
3. **Venue (eventual) — JOSS, not arXiv**, gated on a concrete trigger: **a real external-adoption
   signal (≥3 independent adopters, or a third-party benchmark/paper using hitgate) AND ≥6 months
   public history (≈Dec 2026 earliest).** JOSS-grade is about the *software + research use*, not
   component novelty — so the path is "build adoption → JOSS software paper," which does not require
   the retriever to be novel. arXiv stays **opportunistic-only** (viable only if an endorser appears).
4. **The unlock to watch — academic co-authorship.** Co-authoring with an established researcher
   clears *both* the arXiv endorsement wall *and* the solo-citation penalty (RAGAS's Cardiff
   co-authors are the precedent). If such a relationship becomes available, it changes the venue and
   timing calculus immediately — pursue it over solo-deferral.

**When the gate trips (≈6+ months / on adoption):** run the ~90-minute prior-art + reframing check
the critic flagged (is the label-free retrieval-regression-gate *protocol* formalizable as a JOSS
software-paper contribution, vs already-documented practice?) to set the paper's honest claim — and
prefer co-authorship if available.

## Alternatives considered

- **Write a formal paper (arXiv/JOSS) NOW to bootstrap adoption (signaling).** Rejected: both venues
  are hard-blocked (verified 5-day history / 0 adopters / endorsement wall), and a pre-adoption solo
  paper yields ~0 citations — the signal isn't worth the effort against blocked venues.
- **arXiv as the eventual venue** (per ADR-0006/0008's original wording). Demoted to opportunistic:
  the endorsement gate makes it unreliable for a solo non-academic; JOSS gives a real DOI without an
  endorser. Superseded by this ADR.
- **Skip the blog; pour effort into adoption directly.** Rejected: the blog *is* a cheap adoption
  lever (contrarian-honest content travels) and the honest-methodology angle is the project's brand —
  but only if sequenced with the launch, hence the visibility condition above.
- **Docs-only + CITATION.cff/Zenodo.** Kept as a baseline (a Zenodo release gives a DOI), but not
  citable-in-academia on its own; insufficient as the durable lever.

## Consequences

**Positive.** No effort wasted on a blocked, low-yield paper. The cheap, honest blog runs now and
feeds adoption. The eventual venue (JOSS) is correctly chosen and gated on the maturity/adoption it
actually requires. Co-authorship is named as the real accelerator. The three bets are separable, so
each can be revisited independently.

**Negative / accepted.** The durable-citation lever is pushed out ≥6 months (accepted — it is
literally gated by JOSS's 6-month rule and by needing adopters). The blog has zero citation value and
~90-day reach decay (accepted — it's an awareness/adoption tool, not the citation). If adoption never
materializes, the formal-paper lever never opens (accepted — that's the honest dependency).

**Neutral.** No code changes; this is a writing/venue/timing decision.

## Revisit when

- **≥3 independent external adopters (or a 3rd-party benchmark/paper using hitgate) AND ≥6 months
  public history** → JOSS becomes viable; do the reframing check and submit (prefer co-authorship).
- **An academic co-author / cs.IR endorser becomes available** → re-evaluate arXiv/JOSS *now*; the
  solo-penalty and endorsement wall both fall.
- **The blog gets no measurable traction** after launch → stop investing in blog posts; redirect to
  direct adoption (embedding) and reassess.
- **The contribution becomes genuinely novel** (e.g., a new label-free ranking-eval protocol with
  theoretical grounding, beyond frozen-baseline + per-intent gating) → a real paper becomes possible
  earlier; revisit the blog-grade verdict.
