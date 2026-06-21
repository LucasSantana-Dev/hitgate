# ADR-0008: Ecosystem embedding — earn credibility first (sweep + positioning), then publish, then probe the durable lever

## Status

Accepted (2026-06-21). Decided via `research-and-decide`: 3-agent research (target landscape +
embedding-mechanism/durability + repo integration surface) → `decision-critic` (verdict:
ENDORSE-WITH-CHANGES) → orchestrator verification of the critic's Claims-To-Verify → this record.
Executes the **primary lever of [ADR-0006](0006-reach-strategy-retrieval-gate-positioning.md)**
(reference + usage via ecosystem embedding), now that the harness is a standalone installable
package ([ADR-0007](0007-packaging-harness-as-hitgate.md)).

## Context

ADR-0006 established that the lever which produced *sustained* reference for comparable tools is
**durable embedding** (cited in stable docs / native integration / maintainer partnership), not
virality. With hitgate now a standalone, zero-dependency, importable package, the question is the
**first embedding move**.

Research surfaced a genuine disagreement between two of its own agents, plus a critical mechanism finding:

- **Target landscape** ranked the **Awesome-RAG-Production** list #1 (trivial PR, high acceptance,
  fills the Hit@K/MRR gap that RAGAS/DeepEval/TruLens leave — they are LLM-judge answer-eval tools).
- **Embedding mechanism / durability** found Awesome-lists are **fragile (2–4 yr, ~50% go stale)** —
  "traps for solo tools" — while the **durable** play (5+ yr) is a **docs-PR to LangChain/LlamaIndex
  official docs**, which has a **hard prerequisite: hitgate must be on PyPI first**. It also found the
  **most durable** mechanism is a **native eval-integration** (the RAGAS `integrations.langchain`
  pattern: expose the gate *inside* the framework), 12–20 wk and maintainer-trust-gated.
- **Critical**: hitgate's existing `adapters/` are **retriever-adapters** (map a foreign retriever
  *into* hitgate) = "adoption *by* hitgate users", **not** adoption *by* the framework. The durable
  direction is the **inverse** eval-integration. Retriever-adapters do not, by themselves, drive
  framework embedding.

`decision-critic` (ENDORSE-WITH-CHANGES) flagged the latent conflict: an initial plan made a
retriever-adapter docs-PR the durable PRIMARY — but that reuses the *weak* embedding direction, and it
left hitgate's strongest built-in credibility (a 70-repo benchmark sweep, in progress) **invisible**,
with no path to being surfaced, and proposed publishing to PyPI with **no readiness gate**.

**Verified (orchestrator, this session):**
- The **70-repo auto-benchmark sweep is mid-run and not public** (local results only) — the "benchmarked
  across ~70 real repos, zero tuning" claim cannot yet back a PyPI entry or an Awesome PR.
- The **README still leads with "A pytest-style regression gate for retrieval quality" and the old name
  `evidence-first-rag`** — the ADR-0006 wedge (the honest label-free *retrieval* gate, distinct from the
  answer-eval crowd) and the `hitgate` surface are **not written yet**. A PyPI launch would inherit this
  un-sharpened hook.
- The external precedent claims the critic flagged (LangChain retriever-adapter docs acceptance rate,
  RAGAS eval-integration adoption data, LiteLLM timeline, Awesome churn) are **not cheaply verifiable** —
  so the decision is structured to **defer** the lever choice that depends on them rather than bet on it.

## Decision

**Earn credibility first; publish gated on it; keep the durable-lever choice data-driven.** A
reordered, gated sequence (supersedes the initial "publish-then-docs-PR-reusing-retriever-adapters" plan):

1. **Now — Awesome-RAG-Production PR** (trivial, no deps). A cheap credibility spark that fills the
   Hit@K/MRR gap. Accepted as *fragile* (2–4 yr) — taken because it is ~free, not relied on for durability.
2. **Credibility anchor — surface the 70-repo sweep** as a methodology artifact: a results table + the
   honest framing (Hit@5 saturates because auto-generated queries derive from the code's own symbols; the
   real signal is Hit@1/MRR) + reproduce steps, committed to the repo (`docs/`). This is the
   *earn-the-citation-instead-of-asking* move — the evidence an Awesome entry, a PyPI page, and a docs-PR
   all point at.
3. **Positioning (ADR-0006 Move 1) — prerequisite to publish.** Sharpen the README lead to the wedge and
   make `hitgate` the surface. PyPI inherits this hook; publishing without it risks a launch into the void.
4. **Publish to PyPI** ([ADR-0007](0007-packaging-harness-as-hitgate.md) step 7) — **gated** on (2) and (3)
   existing, so it launches with a story.
5. **Durable lever — as a probe, not a pre-committed bet.** After publish, ship the *cheap* retriever-adapter
   docs guide ("evaluate your LangChain/LlamaIndex retriever with hitgate", reusing the existing adapters)
   and **measure traction**. Build the harder **native eval-integration** (the RAGAS inverse pattern) only
   if the probe data justifies it. The native integration stays explicitly on the table — this avoids the
   path-dependency trap of letting the easy lever saturate demand and foreclose the durable one.
6. **Langfuse integration guide** (parallel, cheap). Reuses the production-ready, tested
   `adapters/langfuse_eval.py`; a 1-page guide, durable-ish, low effort.

**First concrete actions:** the Awesome-RAG-Production PR (today) and finishing + surfacing the sweep
(in progress). Publish and docs-PR follow, gated.

## Alternatives considered

- **Publish to PyPI now, then a docs-PR reusing the retriever-adapters (the initial plan).** Rejected:
  no readiness gate (un-sharpened positioning → launch into the void), and the docs-PR leans on the
  retriever-adapter direction the mechanism research found does not drive framework embedding.
- **Make the native eval-integration the PRIMARY now.** Deferred: 12–20 wk + maintainer trust + 15–25%
  acceptance for a solo tool — premature before there is adoption proof. Kept on the table as the escalation.
- **Awesome-RAG-Production as the primary durable target** (the target-agent's #1). Rejected as *primary*:
  fragile 2–4 yr half-life. Kept as a cheap spark.
- **Comparison-table citations / guest blogs.** Rejected/deferred: fragile (1–3 yr) or one-time spikes.
- **A single-bet strategy.** Rejected: the cheap shots (Awesome, Langfuse) are near-free and parallel; the
  cost is the serialized docs-PR review, which the sequence front-loads credibility against.

## Consequences

**Positive.** Credibility is *built* (sweep + positioning) before it is *spent* (PyPI, docs-PR), so the
launch has a story. The durable-lever choice (retriever-adapter probe vs native eval-integration) is made
on data, not assumption — directly addressing the critic's path-dependency trap. Cheap parallel shots
(Awesome, Langfuse) reuse existing code and cost little. Most steps are repo-local; only the Awesome PR,
the PyPI publish, and the docs-PR are outward-facing (and user-gated).

**Negative / accepted.** PyPI publish slips ~2–3 weeks (time to surface the sweep + sharpen positioning) —
accepted as a prerequisite, not a delay. The Awesome entry is fragile. The durable docs-PR is a 4–8 wk
async review with no SLA and unverified (~60–70% claimed) acceptance — front-loaded credibility is the
hedge. The native eval-integration, if it proves necessary, is a 12+ wk play.

**Neutral.** No code behavior changes; this is positioning, docs, packaging, and outreach.

## Revisit when

- **The sweep is incomplete or stays unsurfaced** → do not publish to PyPI or cite "70 repos"; the
  credibility claim would be hollow.
- **The retriever-adapter docs-PR is rejected, or merges but gets no measurable traction** → escalate to
  the native eval-integration (the durable inverse pattern); do not treat the probe as the destination.
- **The Awesome-RAG-Production list goes stale** (no updates in 12+ mo) → stop relying on it for discovery.
- **A framework maintainer signals interest** → jump straight to the native integration / partnership lever.
- **Positioning still reads as "one more RAG repo"** after the rewrite → rework before publishing (per
  the owner's "not just one more RAG repo" goal).
