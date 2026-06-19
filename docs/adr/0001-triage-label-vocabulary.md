# ADR-0001: Triage label vocabulary

## Context

Setting up the Matt Pocock engineering skills required choosing a GitHub Issues label vocabulary for the triage workflow. Two options were evaluated: the Pocock skill defaults (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) and a hybrid scheme that mixes community-familiar labels with an `agent:*` namespace.

## Decision

Use the Matt Pocock default vocabulary unchanged.

## Alternatives considered

**Option E — Hybrid (`triage`, `needs-info`, `agent:ready`, `human:ready`, `wontfix`)**
Rejected. The primary argument for it was contributor discoverability — community-familiar labels reduce onboarding friction. The README explicitly describes this repo as "a solo operator's personal tool… no SLA," making external contributor discoverability a non-issue for the foreseeable future. The namespace-isolation benefit (guards against third-party bot label collisions) is also irrelevant: the only GitHub Actions workflow is an advisory eval gate that emits no labels.

**Option B — Standard GitHub conventions (`triage`, `needs-info`, `good first issue`, `help wanted`, `wontfix`)**
Rejected. `good first issue` and `help wanted` have community semantics that don't map to the AFK-safe / human-required distinction the triage skill needs. No agent-specific signal.

## Consequences

- `/triage`, `/implement`, and related skills read label strings from `docs/agents/triage-labels.md` (config-driven, not hard-coded) — renaming later costs one file edit + one `gh label edit` batch.
- Labels must be created in the GitHub repo before first use: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`.

## Revisit when

- External contributors begin filing issues or PRs at a regular cadence, and confusion over label semantics is observed.
- A third-party GitHub App is adopted that emits labels with `ready-*` or `needs-*` prefixes.
