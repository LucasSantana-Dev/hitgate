---
title: Context gate: label-free regression gate for agent context (skills, memory)
status: in-progress
date: 2026-11-06
tags: [agent-context, eval, label-free]
---

# Context gate

## Problem

Operators edit CLAUDE.md files, skills and memory notes constantly and never measure the effect. The concrete failure mode with hundreds of skills is trigger collision: a new skill or a reworded description makes an existing skill unreachable for the phrases its author wrote for it. Nobody notices until the agent picks the wrong skill in a live session.

hitgate already has everything needed to catch this as a regression: golden cases mined from the corpus, Hit@K and MRR, a frozen baseline, a compare step with a tolerance in percentage points. What it lacks is a miner for context corpora and a retriever that runs without the `[hybrid]` extra.

## What ships (first vertical slice)

`hitgate-context ROOT [--label L] [--baseline FILE] [--top K] [--retriever module:func]`

1. Mines a golden set from a context root, label-free:
   - `**/SKILL.md` with frontmatter: every `triggers:` or `auto-invoke:` phrase becomes a query; the expected hit is that skill's own `SKILL.md`. Intent `skill-trigger`. The searchable text of a skill is its frontmatter `description` only, because that is what the model sees when it chooses a skill.
   - `**/*.md` with a frontmatter `description` outside a skill folder (memory notes, agent definitions and the like): the description is the query; the expected hit is the note. Intent `note` (memory notes, agent files, anything with a description). The searchable text is the note body with the frontmatter stripped, so the case is not trivially circular.
   - CLAUDE.md sections are not mined in this slice: there is no label-free query source for them that is not the section itself.
2. Runs the cases through `hitgate.run.run` with a built-in stdlib lexical retriever (BM25 over the mined documents). `--retriever` plugs any retriever that honours the existing protocol.
3. Prints the metrics, the per-intent breakdown and the shadowing report: for each miss, which document ranked first instead. Writes `hitgate/context.<label>.json`.
4. With `--baseline`, runs `hitgate.compare.compare` and exits non-zero on a regression beyond the tolerance. A/B over history is two runs at two refs, nothing more.

## Constraints honoured

- Zero runtime dependencies for the context path (pyproject `dependencies = []` stays empty).
- ADR-0012 retrievability caveat applies and is printed: a hit proves the phrase still reaches its skill under this retriever, not that the skill is good.
- ADR-0013 deferred an agent behaviour gate (`hitgate eval-agent`) behind a trigger that expired 2026-09-01 with zero requests. ADR-0015 closes that track and records that the context gate measures discoverability of context, not agent behaviour. EvalView keeps the snapshot-style behaviour gate.
- ROADMAP "not a plugin framework": no plugin loading, one module, one CLI entry point.

## Non-goals

- Judging whether a skill body is well written.
- Measuring the model's actual selection; the lexical retriever is a proxy and the caveat says so.
- Mining CLAUDE.md or standards (future: queries from git log subjects that touched them).
- A Rust rewrite. If the gate proves useful as a git hook, a single static binary with no Python is the natural follow-up project; it is not this slice.

## Acceptance

- `pytest tests/test_context.py` green; whole suite green.
- A real run on `~/.claude` (478 skills, 36 memory notes) completes in under 10 s and lists at least one shadowed trigger.
- Baseline then compare with a deliberately broken skill description shows a regression exit code.

## Measured on 2026-11-06

`hitgate-context ~/.claude/skills` on 590 documents ran in about 4 s: skill-trigger n=1481 Hit@1 0.490 Hit@5 0.719; note n=103 Hit@1 0.835 Hit@5 0.981. Over all of `~/.claude` (899 docs, 1817 cases) Hit@1 0.501. Critic pass (T2 gate) found and we fixed: substring path collisions (`review` inside `code-review`), multi-line descriptions cut at the first line, and an aggregate-only gate blind to a single broken skill; the gate now also fails on any case that hit in the baseline and misses now. The regression test in `tests/test_context.py` reproduces the deliberately-broken-description case with exit code 1.
