# ADR-0013: Adopt EvalView's craft into hitgate — sequenced behind the ADR-0006/0008 credibility gates (run resonance/scout first; ship honesty + scaffolding before the action.yml CTA)

> **Numbering note:** originally drafted as 0012, renumbered to **0013** — `0012-caveat-investment-timing.md` (the repo copy of ADR-0037) was already merged on `main` (PR #54); a stale local checkout hid it during drafting.

## Status

Accepted (2026-06-22). Decided via `research-and-decide`: `adt-research` two-agent
fan-out (EvalView primary-source deep-dive + hitgate surface map) → orchestrator
verification (GitHub API on `hidai25/eval-view`; direct HN Algolia fetch; `grep` of
hitgate's output stream) → `decision-critic` (artifact-only; verdict **NEEDS-REVISION**,
strategic core NOT flipped) → orchestrator verification of the critic's Claims-To-Verify
→ this record. Governs the **distribution/positioning** question only; executes the
post-publish "cheap adoption probes, measure traction" stage of
[ADR-0008](0008-ecosystem-embedding-credibility-first.md) (PyPI publish is DONE).

## Context

A comparable tool, **EvalView** (`github.com/hidai25/eval-view`, "pytest for agents")
was studied for transferable craft. It is a *comp, not a competitor*: it gates agent
tool-call **trajectories**; hitgate gates **retrieval ranking**. The question: what to
borrow, and in what order, without violating hitgate's committed reach strategy.

**Verified facts (orchestrator, this session):**
- **EvalView repo (GitHub API):** 117★, 21 forks, Apache-2.0, v0.8.0, 32 releases in
  ~3 months; a 10.4 KB Marketplace `action.yml` (posts PR comments, uploads artifacts);
  `VS_*` comparison docs; `AGENTS.md`; a zero-arg `evalview demo` and an `evalview init`
  that auto-scaffolds a baseline; a "$0 / no API key" deterministic mode.
- **EvalView's two Show HN posts both flopped** (HN item 46305202 = 1 point; item
  46525535 = 2 points; only the author commented on each). Its 117★ were **not** won on
  Show HN — a clean external confirmation of [ADR-0006](0006-reach-strategy-retrieval-gate-positioning.md)'s
  already-verified base rate (median Show HN ≈ 2 pts ≈ ~3★; "a spike amplifier, not a
  reach builder"; sustained reference comes from ecosystem embedding + cadence + a
  methodology artifact).
- **hitgate surface:** CLI `hitgate-run/-compare/-diff/-generate/-audit-contamination`;
  env-var config; output = JSON + stdout delta tables + `verdict.json`; CI = a copy-paste
  bash snippet (`examples/retrieval-gate.yml`); `hitgate/check.sh` already wraps the full
  gate (build → run → compare → exit 0/1). **No** `action.yml`, **no** PR-comment
  integration, **no** `demo`/`init` command (verified: `pyproject.toml [project.scripts]`).
- **The label-free caveat is prose-only.** `grep` of `hitgate/*.py` / `ragcore/*.py`
  finds the "SELF-INDEXED / retrievability ≠ relevance" caveat only in docstrings and a
  chart title — **not** in `hitgate-run` stdout or the emitted JSON. ADR-0037 item #48
  (a DO-NOW honesty item) landed in README/docs but not in the runtime output stream.
- **The ADR-0006/0008 cheap gates have NOT been run:** no record of the resonance test
  (r/LocalLLaMA + r/MLOps) or the ecosystem scout (cold-contact 2 maintainers); no Show
  HN posted.

**`decision-critic` (NEEDS-REVISION, core not flipped):** the strategy is sound but
**tactically missequenced** — shipping an in-repo `action.yml` (outward-facing infra) before
the ADR-0006/0008 cheap gates run is the exact sequencing error those gates exist to
prevent; `demo`/`init` scaffolding likely outranks the Action because hitgate's real
adoption friction is the baseline-SETUP ritual (generate→curate→freeze), not the CI wiring.
**Claims-To-Verify, checked by the orchestrator:** resonance/scout **not run** (confirmed);
EvalView star-causation **not establishable** (accepted → Action downgraded to
friction-reducer + CTA, not a proven star-driver); adoption friction **unmeasured**
(accepted → `demo`/`init` priority is hypothesis-driven, backed by the EvalView analogy);
caveat-in-output is ADR-0037 **#48 DO-NOW, not deferred** (critic's doubt **refuted** by
direct read of ADR-0037); `action.yml` = pure packaging of `check.sh` (confirmed).

## Decision

**Borrow EvalView's craft (not its features), sequenced behind hitgate's own credibility
gates.** This is a distribution/positioning decision under ADR-0006/0008; it does **not**
reopen ADR-0037 (caveat-mitigation product stays deferred).

**Gate 0 — run the ADR-0006/0008 cheap gates first (~3h; also unblocks the Show HN).**
Resonance test (post the wedge hook to r/LocalLLaMA + r/MLOps; rework if <5 upvotes / 0
comments) + ecosystem scout (cold-contact 2 framework maintainers to validate appetite).
These were already mandated by ADR-0006 and are the prerequisite for any outward-facing
launch material.

**Wave 1A — ship now (repo-local honesty/positioning; NOT outward distribution; not gated):**
1. **Emit the label-free caveat in the runtime output stream** — one structural footer
   line in `hitgate-run` stdout + a `"measures"`/`"caveat"` field in the JSON and
   `verdict.json`. Completes the CLI/JSON portion of ADR-0037 **#48** (DO-NOW). **Sub-gate:**
   the footer wording gets an ADR-0031 honesty sign-off (structural, not an alarmist
   scare-line) before merge.
2. **`docs/COMPARISONS.md`** — hitgate vs RAGAS/TruLens/DeepEval/promptfoo (they judge
   *answers*, need LLM-judge/labels; hitgate gates *retrieval ranking*, label-free) + one
   honest hitgate-vs-EvalView line (retrieval layer vs agent-trajectory layer).
3. **Onboarding craft** — a one-line analogy ("pytest's regression gate, but for retrieval
   ranking — no labels, no LLM judge"), headline the "$0 / no-labels / no-judge" lever, and
   add a **zero-arg `hitgate demo`** plus a **`hitgate init`** that scaffolds the
   generate→curate→freeze baseline ritual. `init`/`demo` is elevated above the Action as the
   higher-ROI friction-reducer (hypothesis, backed by EvalView investing in exactly this).

**Wave 1B — bundle with the gated launch (after Gate 0 passes):**
4. **In-repo `action.yml`** (gate-only; `pip install hitgate[hybrid]` + `bash hitgate/check.sh`
   + inputs `baseline-hit5`/`tolerance`/`retriever`) as the README/launch CTA
   (`uses: LucasSantana-Dev/hitgate@v0.1.0`). Pure packaging; no new logic. Shipped **with**
   the launch material the resonance test gates — **not** independently before the gate.
   Marked "in-repo; not yet Marketplace-listed."

**Wave 2 — gated on a first adoption signal (unchanged):** Marketplace **listing** of the
Action (the credibility-spend step); PR-comment integration; graded verdict tier
(SAFE/INVESTIGATE/BLOCK) + "→ next command" hints.

**Do NOT borrow:** (a) agent-trajectory snapshotting, `forbidden_tools`, model-check,
multi-turn, simulation cassettes, LLM-judge layers — EvalView's owned lane (the agent-gate
extension is separately gated behind ≥3 user requests, close by 2026-09-01); (b) EvalView's
"first run = baseline" snapshot-as-truth model — hitgate's frozen, contamination-audited,
corpus-mined golden set is the more honest design (`audit-contamination` already exists).

## Alternatives considered

- **Ship the in-repo `action.yml` now as a Wave-1 "cheap proof-of-practice" (pre-gate).**
  Rejected per the critic: an `action.yml` is functional outward-facing infra (users `uses:`
  it; the README points at it), so it is discoverable distribution — shipping it before the
  ADR-0006/0008 resonance/scout gates is the sequencing error those gates prevent. Reconciled
  to Wave 1B (bundled with the gated launch), not Wave 1A.
- **Build + list the Action on GitHub Marketplace now (full EvalView parity).** Rejected:
  "spends credibility before earning it" (ADR-0006/0008) at t+0 / 0★ / single-author; a
  broken v1 with no users is a credibility cost. Marketplace listing stays Wave 2 (gated).
- **Lead Wave 1 with the Action as the highest-ROI borrow** (original `adt-research` ranking).
  Rejected: EvalView star-causation is unprovable, so the Action is a friction-reducer + CTA,
  not a proven discovery lever; and it packages only the *last* step of adoption — the real
  friction is the baseline-setup ritual, which `init`/`demo` addresses. `init`/`demo` reordered
  ahead of the Action.
- **Treat the whole thing as ADR-0037-governed (validate-not-build) and defer all of it.**
  Rejected as a category error in the other direction: distribution/positioning craft is
  ADR-0006/0008's domain; the caveat-in-output is ADR-0037's own DO-NOW #48. Only the
  caveat-mitigation *product* (`--validate-against`, PPI, naturalization) is ADR-0037-deferred,
  and none of that is borrowed here.
- **Do nothing (keep the bash snippet).** Rejected: leaves the core "$0 / no-labels" lever
  under-stated, the caveat absent from the output stream, and the CI-gate identity without a
  drop-in form.

## Consequences

**Positive.** Honesty/positioning craft (caveat-in-output, COMPARISONS, sharper hook) ships
immediately and is ADR-0031-consistent; the cheap ADR-0006/0008 gates run before any
outward spend (de-risks the launch for <1 day); `init`/`demo` attacks the real adoption
friction; the Action ships as a reversible, gate-only CTA bundled with a validated launch;
EvalView's owned lane stays uncrossed. The EvalView Show HN flop is folded in as confirming
evidence for the existing reach strategy — no strategy change required.

**Negative / accepted.** `init`/`demo` priority rests on an analogy, not measured hitgate
usage (0 external users) — accepted as cheap-to-build and cheap-to-be-wrong. The in-repo
`action.yml` adds a small versioning surface (mitigated: SHA-pin + bump only on a `hitgate`
release; no Marketplace sync until Wave 2). The caveat footer is a fragile design constraint
(mitigated by the ADR-0031 wording sub-gate). If the resonance test fails, Wave 1B + the
launch are reworked, not shipped.

**Neutral.** No retriever/gate behavior changes; this is output text, docs, a scaffolding
command, and a packaging file. MIT/self-hosted — zero lock-in; greenfield migration (0
external users).

## Revisit when

- **Resonance test fails** (<5 upvotes / 0 comments on the hook) → rework the hook before
  shipping Wave 1B or any launch material; Wave 1A still ships (it is repo-local honesty).
- **Ecosystem scout finds no viable integration target** → lead with the methodology
  artifact + Show HN only; do not invest in framework embedding yet (ADR-0008).
- **First external adoption signal** (≥1 credible "I ran it on my retriever", OR an external
  issue requesting it, OR ≥25★ / sustained ≥50 PyPI downloads/mo ×2) → promote the Action to
  Marketplace (Wave 2), build PR-comment + graded verdict tier.
- **`init`/`demo` ships but onboarding friction reports point elsewhere** (e.g. CLI UX,
  docs) → reprioritize the next adoption work to the measured bottleneck.
- **A funded incumbent ships a label-free retrieval-ranking gate as a GitHub Action** → the
  packaging wedge is neutralized; fall back to the honesty/methodology angle (ADR-0006).
- **No Show HN / resonance test runs within 30 days** → the whole launch posture is stale;
  reopen ADR-0031/0037 (their timing assumes an imminent launch).
