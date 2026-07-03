# ADR-0013 — hitgate Constellation: Complementary Projects Decision

**Status:** ACCEPTED — 2026-06-22  
**Decided via:** `/research-and-decide` (adt-research Phase-0 scrape → decision-critic NEEDS_REVISION → orchestrator claim verification)  
**Related:** ADR-0031 (launch positioning) · ADR-0032 (one extraction at a time) · ADR-0012 (caveat timing)

---

## Context

hitgate 0.1.0 is live on PyPI. The question: what complementary project should be built alongside it, drawing on the same "gate-not-log" DNA (freeze a baseline, auto-generate a golden set, gate in CI)?

Four candidates were evaluated via a Phase-0 demand scrape (GitHub, web, HN, arXiv, 2026-06-22).

---

## Candidates evaluated

| Candidate | Verdict | Key evidence |
|-----------|---------|-------------|
| **Standalone agent-regression-gate** | SKIP | EvalView (hidai25/eval-view, 117★, v0.4.0, HN Show HN, GitHub Marketplace) owns "pytest for agents" with $0/no-LLM-judge mode. AgentAssay (5★, arXiv 2603.02601) at research stage. |
| **Chunking-quality docs story** | SHIP NOW | hitgate already measures chunking impact (change chunk_size → re-run → see Hit@K delta). Not documented. ~1h. Different from Braintrust/DeepEval (those need LLM judge; hitgate measures retrieval-side impact). |
| **Agent-gate as hitgate extension** | DEFERRED (tiered gate) | Demand unverified. EvalView's 117★ confirms the agent-gate space is taken in snapshot/diff form. hitgate's corpus-derived auto-generation is a different form but has no demand signal yet. |
| **Embedding-drift gate** | SKIP | Solved by: pin embedding model version (config) + Evidently/Whylabs + EvalView model-check. No hitgate wedge. |

---

## Decision

### Immediate (ship with / alongside Show HN)
**Chunking docs story:** add a "validate chunking config changes with hitgate" use-case example page to `docs/`. Cost ~1h. Explicitly exempt from the validate-not-build gate because:
- Cost is negligible (~1h, deletable in minutes)
- Differentiation IS real: hitgate measures chunking by its *retrieval impact* (Hit@K delta), while Braintrust/DeepEval score chunking quality via LLM judge — different layer
- Deepens existing positioning without adding scope

### Deferred (tiered, time-boxed)
**Agent-gate hitgate extension (`hitgate eval-agent`):** auto-fingerprint tool-call traces, diff against baseline in CI — the hitgate corpus-auto-generation principle applied to agent traces.

| Phase | Trigger | What ships |
|-------|---------|-----------|
| Phase 1 | ≥1 agent-eval request within 30 days of Show HN | `hitgate eval-agent --help`, one trace recorded + diffed |
| Phase 2 | ≥3 requests **or** external contributor opens a PR | `examples/agent-gate.yml` CI workflow ships |
| **Close** | 0 requests by 2026-09-01 | Declare closed in a follow-up ADR entry; do not silently defer |

The gate is explicit and time-boxed to prevent silent veto.

### Skip permanently
- Standalone agent-regression-gate product (EvalView owns the form)
- Embedding-drift gate (config + incumbents solve it)

---

## The critical distinction: EvalView vs. hitgate label-free

EvalView "label-free" = **snapshot first-run as baseline** (record/replay approach — you run the agent once, it captures behavior).  
hitgate "label-free" = **auto-mine golden pairs from corpus** (corpus-derived; never ran the retriever to define "correct").

These are genuinely different forms. The agent-gate extension, if built, would apply hitgate's form: auto-generate agent test cases from tool schemas/docs without a first-run. Demand for this form is unverified as of 2026-06-22.

---

## Alternatives considered

| Option | Verdict |
|--------|---------|
| Build standalone agent-gate product now | Rejected — EvalView (117★) owns "pytest for agents"; the hitgate form difference is unproven demand |
| Skip chunking docs as "unvalidated" | Rejected — cost ~1h, differentiation real, safe to ship; the validate-not-build gate applies to features, not one-page docs |
| ≥3-request gate with no time box (original recommendation) | Revised — critic correctly identified this as a silent veto; made explicit + time-boxed (close by 2026-09-01 if no signal) |
| Build agent-gate unconditionally | Rejected — hitgate at 0 traction; agent-gate on an unstable v0.1.0 API creates tech debt without validated demand |

---

## Consequences

**Positive:** chunking docs deepens positioning for free; agent-gate path stays open with a clear tripwire; EvalView's HN post validates Show HN channel (same "I built a testing tool for AI" narrative, distinct angle).

**Negative:** if agent-eval demand is real and hitgate misses the window, EvalView captures the mind-share before hitgate can extend. Accepted: the risk of building without demand is higher than the risk of a late move on a validated signal.

**Neutral:** the "gate-not-log" constellation idea survives; it just waits for hitgate to prove the pattern before extending it.

---

## Revisit when

- ≥1 agent-eval request within 30 days of Show HN → open Phase 1
- ≥3 requests or external contributor → open Phase 2
- 0 requests by **2026-09-01** → close agent-gate track, record in this ADR
- EvalView star count crosses 1k★ → agent-gate window closes; hitgate form difference must be meaningfully validated before building
- hitgate Show HN lands flat (crickets, <50 upvotes, 0 requests) → ADR-0031 disconfirmed; do not invest in constellation at all

---

## Decision-critic reconciliation (2026-06-22)

**Verdict: NEEDS_REVISION** — critic correctly flagged:
1. EvalView star count conflated with AgentAssay's 5★ (EvalView is actually **117★**) → "owns it" claim strengthened
2. ≥3-request gate was a silent veto without time box → revised to tiered + 2026-09-01 close date
3. Chunking docs not validated against the meta-lesson → resolved: cost ~1h, differentiation real (retrieval-side ≠ LLM-judge-side)
4. Asymmetry (chunking ships regardless; agent-gate doesn't) → acknowledged explicitly; justified by cost difference
