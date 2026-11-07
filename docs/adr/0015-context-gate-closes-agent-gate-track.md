# ADR-0015: Context gate ships; the agent-gate track of ADR-0013 is closed

**Status:** ACCEPTED, 2026-11-06
**Related:** ADR-0012 (retrievability caveat), ADR-0013 (agent-gate deferred behind a time box)

## Context

ADR-0013 deferred `hitgate eval-agent` (an agent behaviour gate) behind an explicit tripwire: close the track if nobody asked for it by 2026-09-01. Nobody did. The ADR required the closure to be recorded, not silently deferred.

Meanwhile a different, concrete pain surfaced in the operator's own setup: hundreds of skills and notes, edited daily, with no measurement of whether an edit makes a skill unreachable for the phrases its author wrote for it. That is a retrieval question, and hitgate already has the metric, the baseline and the compare step.

## Decision

1. The agent behaviour gate track is **closed**. EvalView keeps snapshot-style behaviour gating; hitgate does not grow one.
2. hitgate ships `hitgate-context`: a label-free gate over agent context (skills, memory and other notes). It mines cases from the corpus itself (trigger phrases to their skill, note descriptions to their body), scores them with a stdlib BM25 proxy or any `--retriever`, and gates with the existing compare step. Spec: `docs/specs/2026-11-06-context-gate/spec.md`.
3. The ADR-0012 caveat applies verbatim and is printed on every run: a hit means the phrase still reaches its own document under this retriever, not that the document is good or that the model would pick it.
4. ROADMAP's "not a plugin framework" stance holds: one module, one entry point, zero runtime dependencies.

## Measured (2026-11-06, operator's `~/.claude/skills`, 590 documents)

| Intent | n | Hit@1 | Hit@5 |
|---|---|---|---|
| skill-trigger | 1481 | 0.490 | 0.719 |
| note | 103 | 0.835 | 0.981 |

Half of the trigger phrases do not rank their own skill first under the lexical proxy. That number is the baseline to gate against, not a quality verdict. The aggregate gate alone cannot see one broken skill among 590 (one skill moves Hit@5 by about 0.2pp), so the gate also fails on any case that hit in the baseline and misses now.

## Reopen

- Someone asks for an agent behaviour gate in hitgate (reopens ADR-0013's track, with the same tiered gate).
- The lexical proxy disagrees with observed skill selection often enough to matter: then measure with a dense `--retriever` and compare.
- CLAUDE.md sections get a label-free query source (git log subjects that touched them): then extend the miner.
