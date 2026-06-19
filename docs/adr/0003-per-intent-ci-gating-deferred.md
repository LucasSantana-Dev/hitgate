# ADR-0003: Per-intent CI gating deferred — visibility-only for now

## Context

Adding `by_intent` grouping to `eval/run.py` (ADR-0002) creates per-class metrics
(`retrieval`, `indexing`, `infrastructure`). The question: should `eval/check.sh` be
extended to gate CI on per-class regressions, or should per-intent output remain
visibility-only?

The existing gate compares only top-level metrics (`mrr`, `hit@1`, `hit@3`, `hit@5`)
against a frozen baseline with ±5pp tolerance.

## Decision

Per-intent CI gating is deferred. `by_intent` is printed in eval output and included
in the JSON file, but `check.sh` is unchanged — it does not compare per-class metrics.

## Why deferred

Three blockers, all present at time of decision:

1. **No per-intent baseline exists yet.** The `intent` field has not been added to
   golden cases; no measured per-class metrics exist to freeze as a baseline.

2. **SNR risk at current sample sizes.** `infrastructure` has n=3 cases. A single miss
   swings Hit@5 by 33pp — far exceeding the ±5pp gate tolerance. Gating now would
   produce constant false positives, causing the gate to be ignored or disabled.

3. **No in-flight roadmap item requires per-intent gating.** Roadmap items #2 and #5
   list stratified measurement as a *prerequisite* (observability), not a gating target.
   No planned change demands per-class regression detection right now.

## Alternatives considered

**Gate immediately with the same ±5pp tolerance**
Rejected. n=3 for `infrastructure` makes 5pp unachievable — one case miss equals 33pp
regression. The gate would fire on noise, eroding trust in CI.

**Selective gating (gate `retrieval` only, n=5)**
Deferred alongside full gating. `retrieval` has n=5 (one miss = 20pp), still noisy
relative to the 5pp threshold. Revisit when `retrieval` has ≥10 cases.

## Consequences

- `check.sh` is unchanged. Future developers should check this ADR before adding
  per-intent gating to understand the SNR constraint.
- Per-intent metrics are observable on every eval run — visible in stdout and in the
  eval JSON. A developer who checks the output can catch per-class regressions manually.
- The deferral is explicit, not implicit. The trigger for revisiting is documented below.

## Revisit when

**All of the following are true:**

1. The first per-intent baseline has been captured (`eval/run.py` with `intent`-tagged
   golden cases has been run and its JSON committed as the new baseline).
2. Per-class Hit@5 variance is <5pp across ≥2 consecutive runs on the same codebase
   (i.e., the classes are stable enough for a 5pp tolerance to be meaningful).
3. A roadmap item explicitly targets improvement in a specific intent class, or a
   silent per-class regression has been observed in practice and missed by the
   aggregate gate.

Until all three are true, do not add per-intent comparisons to `check.sh`.
