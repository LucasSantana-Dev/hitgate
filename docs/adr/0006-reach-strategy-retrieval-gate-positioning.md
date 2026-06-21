# ADR-0006: Reach strategy — position as the honest label-free *retrieval* regression gate, ship the harness standalone, launch via Show HN (not a metric badge)

## Status

Accepted (2026-06-20). Decided via `research-and-decide`: 3-agent web/repo research → `decision-critic`
adversarial review (verdict: ENDORSE-WITH-CHANGES) → orchestrator verification of the critic's
Claims-To-Verify → this record.

**Amended 2026-06-21** (see *Update 2026-06-21* at the end): a second research+critique pass verified the
Show HN base-rate and **revised Move 3** and **reset the primary goal to reference + usage** (reach is a
bonus, not the objective). Moves 1 and 2 are unchanged and reinforced.

## Context

The project has the substance of a good tool but no reach: it reads as "one more RAG repo." The
owner's stated success signal is **reach / reference** (stars, citation, being recommended) — explicitly
**not** building a funded product or displacing enterprise incumbents. The question: what is the
highest-leverage move toward reach?

An initial brainstorm converged fast on *"ship `pip install rag-eval`, then a reproducible-RAG GitHub
badge/Action as the viral multiplier."* Research and an adversarial review dismantled most of that and
reframed it. The findings (all verified this session unless noted):

**Market shape.** The RAG-eval space is crowded and funded — promptfoo (22.4k★, acquired by OpenAI),
DeepEval (16.3k★, YC), RAGAS (9k★, YC, ~5M evals/mo, the de-facto standard), TruLens (Snowflake),
Arize Phoenix (Sequoia). A solo unfunded project cannot win that game on features or distribution spend.
**But** nearly every incumbent evaluates RAG **answers** (LLM-as-judge faithfulness / relevance /
groundedness of generated text). RAGAS `context_precision`/`recall` and continuous-eval's retrieval
metrics **require ground-truth context (labels)**; BEIR/MTEB do pure retrieval but require labeled qrels
and are fixed academic benchmarks, not "run on your own corpus." The narrow, contested-but-real gap:
**corpus-aware retrieval-*ranking* regression-gating on your own corpus, without ground-truth labels.**

**Differentiation (skeptic's read).** "Retriever-agnostic" is table stakes; "label-free" is claimed by
everyone. The one **genuinely** differentiated trait is **radical honesty** — publishing the ablation
where the *simple* baseline wins (BM25-only Hit@1 0.752 vs hybrid 0.663), leaving misses in the
benchmark, publishing a miss taxonomy. "Regression-gate-in-CI-by-default" is somewhat defensible.

**Reach mechanics.** A `Hit@5=0.94` GitHub badge **credentials nothing** to a viewer who doesn't already
know retrieval eval — metric badges only spread when the metric has cultural weight *outside* the domain
(coverage %, build-passing). It would sit inert. PyPI search is effectively invisible for niche tools.
The highest-yield lever for a solo unfunded tool is a **timed Show HN** (Tue–Thu, 9–11am PT) backed by
reproducible honest methodology, with a Simon Willison newsletter pickup as a possible multiplier.

**Verified repo facts that reshaped the plan:**
- `pip install rag-eval` is **impossible** — the PyPI name is taken by a dormant-but-real same-space project.
- A `pyproject.toml` already exists but packages **only `ragcore`** (the retriever) — the half the README
  itself calls "just the reference implementation, not the product." The `eval/` harness (the stated
  product) is **not packaged and not importable**; adopting it means cloning and copying `eval/`.
- `evidence-first-rag` is **not published on PyPI** → zero downstream users → re-scoping the package is a
  no-risk greenfield change, not a breaking migration.
- The `--retriever module:callable` protocol **already works** (`eval/run.py:load_retriever` resolves any
  callable via `importlib`; only `builtin_retriever()` imports `ragcore`). So making the harness adoptable
  is a *packaging* job, not new functionality.

## Decision

Reframe the reach strategy from "package + badge" to **position + standalone harness + timed launch**,
gated by a cheap pre-launch validation. Four moves:

**Move 0 — Validate before building the launch (de-risk, ~3h).** Draft the positioning line and the
"vs RAGAS/DeepEval" comparison; test the wedge with 3–5 retrieval-eval practitioners (does
"label-free + honest + *retrieval-ranking* gate" read as a strength or as niche/incomplete?). Sanity-check
the Show HN base rate for similar methodology/dev-tool posts. If the wedge doesn't resonate or the base
rate is poor, fall to the contingency ladder in Move 3 before investing in a launch.

**Move 1 — Positioning (the binding constraint; near-zero code).** Sharpen the one-line wedge to:
*"The honest, label-free **retrieval** regression gate — measure your retriever's ranking quality on your
own corpus, with no labels, as a CI gate; and we publish the benchmark where our own baseline loses."*
Add an explicit "when to use this vs RAGAS/DeepEval" decision line (they judge generated **answers**;
this gates **retrieval ranking** without labels). Lead with the radical-honesty proof.

**Move 2 — Re-scope the package (fixes the verified weakest link).** Invert `pyproject.toml` so the
**harness** is the installable, retriever-agnostic, **zero-base-dependency** package; the hybrid retriever
(`ragcore`) becomes a `[hybrid]` optional extra. Make `eval/` importable
(`from rag_eval import run` / `python -m rag_eval run --retriever mod:fn`) by moving it into a
`src/`-layout package and replacing the `sys.path` hacks. Add a <2-minute "run the gate on YOUR retriever"
path. Lean package name: **`retrieval-gate`** (available; on-message: *retrieval*, not RAG-answer; *gate*
= regression gate) — `rageval` is the discoverability-optimized fallback. Confirm the final name at build.

**Move 3 — Launch (the actual reach lever), with an explicit fallback ladder.** A timed Show HN
(Tue–Thu, 9–11am PT) + a methodology post built on the honest finding, pointing at the standalone package.
The CI badge ships as *proof-of-practice only* — not marketed as the growth mechanism.
**If the launch underperforms** (below a pre-set star/upvote floor) **or Willison doesn't pick it up**,
fall to, in order: (a) direct outreach to named retrieval-eval practitioners (RAGAS/continuous-eval users,
LLM-app builders); (b) academic framing (short methodology preprint / workshop note); (c) the durability
path below.

**Durability path (complements reach; addresses "is this just a one-cycle narrative").** Pursue embedding
the gate in the workflow of a few heavy users (a framework maintainer or LLM-app team adopting it as their
internal retrieval regression gate, with a citation). Sustained reference from real usage outlasts a launch
spike — and is what turns "highlighted" into "relevant."

## Alternatives considered

- **Badge-first reach (the original brainstorm's multiplier).** Rejected: a domain-metric badge credentials
  nothing to non-experts and sits inert. Kept only as proof-of-practice.
- **Name it `rag-eval`.** Rejected: taken on PyPI by a dormant-but-real same-space project.
- **Community corpus leaderboard now.** Deferred: high effort, presupposes the reach the project doesn't
  yet have. Reopen once a launch has produced a baseline audience.
- **Compete with RAGAS/DeepEval on features.** Rejected: funded incumbents, heavy table-stakes overlap,
  wrong game for a solo unfunded maintainer.
- **Keep `pyproject.toml` shipping `ragcore`.** Rejected: it packages the half the README calls "not the
  product," leaving the retriever-agnostic-harness claim aspirational.

## Consequences

**Positive.** Plays to the only defensible asset (honest methodology) and a real gap (label-free retrieval
*ranking* eval) instead of competing where the project loses. Move 2 makes the central claim real and is
verified no-risk (no PyPI users, `--retriever` already works, clean refactor). Most effort is positioning
and a launch, not code.

**Negative / accepted risks.** The reach lever (Show HN landing) is **externally contingent and its
base-rate variance is unverified** — the decision's single point of failure, mitigated (not eliminated) by
Move 0 validation and the Move 3 fallback ladder. "Radical honesty" may be a one-cycle narrative win rather
than a durable moat — mitigated by the durability path. The "no SLA / personal tool" framing may deter
mid-market adopters; accepted, because the goal is reference, not enterprise sales. An incumbent could ship
a "label-free retrieval gate" extension and neutralize the wedge — accepted: reach doesn't require a moat,
and first-mover + the honesty narrative + being the reference implementation is the play.

**Neutral.** No production code behavior changes; the retriever and gate are unchanged. The work is
packaging, docs, and outreach.

## Revisit when

- **Move 0 fails** — the wedge doesn't resonate with practitioners, or the Show HN base rate for comparable
  posts is poor → switch primary strategy to practitioner outreach / academic framing before launching.
- **The launch underperforms** the pre-set floor → execute the Move 3 fallback ladder; do not re-attempt
  the same launch unchanged.
- **An incumbent ships label-free retrieval-ranking regression gating** → the gap is closed; re-evaluate the
  wedge (likely pivot to the honesty/reproducibility angle alone, or to the durability path).
- **A heavy user adopts and cites the gate** → double down on the durability path over further media pushes.

## Update 2026-06-21 — base-rate verified; primary goal reset to reference + usage; Move 3 revised

A second `research-and-decide` pass verified the one claim ADR-0006 left open (Show HN as the primary reach
lever) with a 4-agent web-research fan-out, and a second `decision-critic` review (ENDORSE-WITH-CHANGES)
challenged the result. The findings changed the **goal** and **Move 3**. Moves 1 and 2 are unchanged and
reinforced (a reference/usage strategy needs the standalone harness as its credible artifact even more than
a media strategy did).

**Verified base rates.**
- arXiv 2511.04453 is real but reports the **mean** (121/189/289 stars at 24h/48h/1wk) on a
  survivorship-filtered AI-tool sample; it states the median is "much lower." Cross-sourced (Daniel King's
  188k-post analysis, Sturdy Statistics 2025, Anton Tarasenko): **median Show HN post ≈ 2 points ≈ ~3
  GitHub stars; ~89% score below 10 points; ~94% below 50.** A niche tool's *expected* outcome is a flop —
  the 289 was the mean of the winners. **Show HN is a lottery, not a reliable lever.**
- Traced case studies (RAGAS, Promptfoo, Instructor, Ollama, LiteLLM): sustained reference came from
  **credible-founder voice + ecosystem embedding (being cited/integrated by a bigger project) + (for eval
  tools) an academic/methodology artifact.** *Show HN was no one's primary lever — "a spike amplifier, not
  a reach builder."*
- The "simple baseline wins" honesty angle **did travel** 2024–26 but has decayed from contrarian to
  **resolved consensus** (hybrid is table-stakes) — the hook must be sharper than "BM25 beats dense."
- Contrarian methodology **posts** travel further than tool launches but are themselves survivorship-filtered
  and convert worse; the "2–4×" travel figure and a "~30–40% Simon Willison pickup" are **soft inferences,
  treated as upside, not plan** (Willison has never reviewed RAG-eval tools — only evals-as-practice).
- **Meta-finding: there is no reliable high-yield reach lever for a solo unfunded niche tool.** Every
  high-upside path is a lottery; the reliable paths produce small reach.

**Primary goal (owner decision, 2026-06-21): reference + usage.** Optimize to be the cited reference for
label-free retrieval-eval / drift detection **and** to get a handful of teams running the gate in CI. A
viral post or Show HN spike is a **bonus**, not the objective. (Supersedes ADR-0006's implicit reach/stars
framing.)

**Move 3 — REVISED (supersedes the original Move 3).**
- *Spine (primary — reference + usage):*
  1. **Ecosystem embedding.** Concrete first step (not luck): the repo already ships `adapters/` for
     LangChain + LlamaIndex — submit integration examples to their eval docs, open a "retrieval evaluation"
     subsection PR to the Awesome-RAG lists, and scout 3–5 actively-maintained RAG frameworks' issue
     trackers for retrieval-eval gaps to integrate against. This is the LiteLLM/Instructor "cited-in-docs"
     pattern — the only lever that produced *sustained* reference in the case studies.
  2. **arXiv methodology note** (the RAGAS legitimacy-backfill pattern): a short write-up of the label-free
     regression-gate methodology + the honest cross-corpus ablation (including where the system loses).
     Treat as a 6–18-month citation bet; sequence so the blog post can precede formal publication.
- *Opportunistic reach (bonus, cheap shots):*
  3. **Methodology post** with a sharper hook than "BM25 wins": *"a label-free regression gate that catches
     retrieval drift without labels — here's the honest ablation, including where our own system loses."*
     Own blog + Medium + dev.to.
  4. **Show HN** of the standalone harness, 1–2 weeks after the post, as a *conversion* step. Calibrate to
     the median: base case is a flop (~3–7 stars); pre-set floor (10 pts @ T+4h, 40 @ T+12h); exceeding it
     is upside.
- *Mandatory cheap gates before committing (from the second critic review):*
  - **Resonance test (~2h):** post the hook to a relevant subreddit; if <5 upvotes / 0 comments, rework the
    hook before the post.
  - **Ecosystem scout (~3h):** identify 3–5 viable integration targets and cold-contact 2 maintainers to
    validate appetite *before* investing weeks in embedding.
- **Badge:** unchanged — proof-of-practice only, never marketed as growth.

**Plan D (if spine + reach both disappoint):** narrow to the micro-niche — be the reference implementation
and cited methodology for label-free retrieval drift detection, accept small reach, and let usage accrue
from the few genuinely label-constrained teams. Do not chase virality on retries.

**New revisit triggers.**
- Resonance test fails → rework the hook before any launch.
- Ecosystem scout finds no viable target in ~3h → Phase C isn't yet actionable; lead with the arXiv note +
  post only.
- Methodology post median-flops **and** Show HN flops → execute Plan D; do not re-attempt the same launch.
- A heavy user adopts/cites the gate → double down on embedding over media.
