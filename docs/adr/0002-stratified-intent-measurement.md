# ADR-0002: Stratified per-intent measurement via manual tagging

## Context

The eval harness (`eval/run.py`) reports aggregate Hit@K / MRR over 12 golden cases.
All 12 share `expect_scope: "code"`, so the existing `by_scope` breakdown yields a
single row — no per-class visibility into *where* the retriever is strong or weak.
Roadmap item #4 calls for classifying queries by intent and reporting per-class metrics
as a prerequisite for honestly evaluating every other roadmap item.

Two approaches were evaluated:
- **Option A** — add an `intent` field to each golden case by hand; group results
  `by_intent` in the harness (mirroring the existing `by_scope` logic).
- **Option E** — same as A, plus a runtime classifier to tag live queries at
  query time.

## Decision

Use Option A: manual tagging of golden cases + `by_intent` grouping in `eval/run.py`.
Do not ship a runtime classifier.

Intent taxonomy (3 classes, validated against all 12 golden cases):

| Class | Meaning | n |
|-------|---------|---|
| `retrieval` | Query-time behaviour — fusion, ranking, reranking, fallback | 5 |
| `indexing` | Index-time behaviour — chunking, embedding, source classification | 4 |
| `infrastructure` | Config defaults, exclusions, eval harness | 3 |

All classes n≥3, no ambiguous cases.

## Alternatives considered

**Option E — manual tags + runtime classifier**
Rejected. The eval goal is per-intent measurement on a fixed golden set — a static
problem that needs no classifier. A runtime classifier solves a different problem
(tagging novel live queries) with no current demand: the repo is a solo operator's
personal tool with no monitoring, dashboards, or instrumentation in the roadmap.
Shipping a classifier whose correctness cannot be validated against golden-case tags
creates divergence liability with no measurable upside. Deferred until a concrete
use case materialises.

**LLM-based classifier**
Rejected outright. Violates the reproducibility constraint (same query → same result)
unless seeded and pinned. Adds API dependency. Nondeterminism would invalidate
per-intent metrics over time.

**Embedding-based k-NN classifier**
Rejected. At 12 golden cases there is no held-out validation set — the training set
IS the eval set. A k-NN classifier trained on it would overfit and cannot be validated.

## Consequences

- `eval/run.py` gains a `by_intent` block mirroring the existing `by_scope` grouping
  (~10 lines).
- `eval/golden.demo.jsonl` gains an `intent` field on each case.
- Per-intent Hit@K is now a prerequisite gate for evaluating other roadmap items
  (contextual chunk prefixing, reranker tradeoff table, etc.) — if a change improves
  aggregate Hit@5 but regresses `retrieval`-class, that is visible.
- Taxonomy is append-safe: new golden cases can add new intent classes without
  breaking existing metrics.

## Revisit when

- The eval set grows past ~100 cases and manual tagging becomes a bottleneck — at
  that scale, a regex-pattern or embedding-based classifier becomes worth validating.
- A concrete use case for live-query classification materialises (e.g., per-intent
  latency monitoring, per-intent reranker gating).
