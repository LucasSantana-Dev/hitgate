# Part 1 outline: "A gate you have never seen fail is not a gate"

> Title locked 2026-08-07. Full draft: `part-1-draft.md` (2,663 words, sourced).

Series: **Eval gates for delivery teams: label-free CI quality gates for retrieval and agents**
Part 1 of 3. Target: Thoughtworks Insights, then InfoQ, then dev.to (canonical cross-post).
Status: outline. Drafted 2026-08-07 from the market discovery in `decision_portfolio_next_bet_2026-08-06`.

## Why this angle

Two independent research tracks converged on the same white space: the CI/CD *engineering*
discipline of eval gates. The field already has metric design (RAGAS, DeepEval), platform
comparisons (Braintrust, LangSmith, Langfuse), agent trajectory eval (Anthropic), and academic
flakiness papers. What nobody has written: how a delivery team makes a gate that is *trustworthy*
under noise, on a run budget, without an annotation budget.

Deliberately NOT leading with "a reference architecture." Fowler owns that framing for GenAI
products. The architecture diagram lands in Part 3 as the artifact, not the pitch.

## Thesis

Most teams building LLM systems have one of two broken gates:

1. **No gate**, because they were told they need a labeled golden set and cannot afford one.
2. **A gate that cannot fail**, or one that fails at random, because nobody measured whether the
   eval can detect a real change in the first place.

Both are fixable without labels. The fix is to stop asking "is this output good?" and start asking
"did this change move anything, and is that movement bigger than my noise floor?"

## Structure

### 1. Cold open: the green gate that could not fail
Concrete scene. A retrieval change ships. The eval gate is green. It was always going to be green.
Show the number that looked fine and the reason it was meaningless.

Real material available: hitgate's own 24-case golden set was **too small to discriminate**. BM25-only
and dense-only both scored Hit@5 = 0.826, so the ablation was inconclusive. The gate was reporting
a number, not a signal. That is the whole article in one artifact, and it comes from my own repo
admitting its own instrument was broken.

### 2. Why "get a golden set first" stalls delivery teams
- Annotation cost lands before any value is proven.
- Golden sets go stale as the corpus moves; contaminated cases quietly become unwinnable.
  (hitgate ships `audit_contamination.py` precisely because 2 of 101 cases were unwinnable.)
- One user, no traffic, no A/B. The advice assumes a scale most teams do not have yet.
- Note honestly: reference-free *metrics* are well covered (RAGAS faithfulness, answer relevancy).
  The gap is reference-free *regression gating*: every mainstream tool still needs a curated or
  synthetic golden set to establish the baseline it gates against.

### 3. Reframe: gate on deltas, never on absolutes
The core move. An absolute score on a self-indexed corpus is optimistic by construction and means
nothing across projects. A *delta against a frozen baseline* is a regression signal and is exactly
what a test suite gives you.

State the honest caveat up front, the way the tool does: label-free goldens measure
retrievability and regression, not human-judged relevance. Claiming otherwise is where this
category loses credibility.

### 4. Where the goldens come from when you have no labels
Mine query to chunk pairs from distinctive terms already present in the corpus. No annotation,
no traffic, no judge. Show the shape of a mined case and what makes a term "distinctive" enough
to anchor one.

### 5. The section nobody else has written: prove the gate can fail
This is the original contribution. Before trusting any eval gate, run an ablation that *should*
hurt, and confirm the gate notices.

- hitgate's discriminability rule: an ablation must move the metric by **>= 5pp** for the eval set
  to count as able to detect real change.
- At 24 cases: BM25 and dense tie at 0.826. Inconclusive. Gate not trustworthy.
- At 99 cases: dense-only drops Hit@5 by 6.1pp, BM25-only by 8.1pp. Both clear the bar. Gate earns trust.
- Generalize the principle: a gate you have never seen fail is not a gate. This is the same
  discipline as mutation testing, applied to evals.

Tie to the measured noise floor: how many runs before a diff is real. Flag honestly that no
mainstream eval tool models evaluator uncertainty or gates on statistical significance today.
Teams treat N=1 as truth.

### 6. Let the measurement contradict you
Credibility section. hitgate's own 99-case ablation says **BM25-only beats the hybrid design on
Hit@1 (0.737 vs 0.636) and MRR (0.803 vs 0.784)**, while hybrid wins Hit@5 and is the only mode
reaching 1.0 across all three intent classes. The design survives on a *narrower* claim than it
started with. Publishing the contradiction is the point: a gate that only ever confirms you is
decoration.

### 7. What this does not do
- No answer quality. No faithfulness, groundedness, relevancy. Different layer.
- No claim of human-judged relevance.
- Not a replacement for judged evals where the stakes need them.

### 8. Handoff to Part 2 and 3
- Part 2: the retrieval case end to end, with the cross-corpus evidence (8 corpora, Python /
  TypeScript / React / Next.js; Hit@5 = 1.0 on six of eight; the Criativaria corpus at 0.741
  exposing a real ceiling where no retrieval signal distinguishes sibling UI components).
  Finding worth its own section: **corpus structure predicts retrieval performance more than
  language does.**
- Part 3: generalizing the same gate shape to agent outputs, plus the reference architecture:
  gate placement, run budget, cost per PR, threshold selection, rollback rules.

## Evidence inventory (all primary, all mine, all reproducible)
| Claim | Source |
|---|---|
| 24-case set could not discriminate | `docs/METHODOLOGY.md` historical ablation |
| 99-case set clears the 5pp discriminability gate | `docs/METHODOLOGY.md` ablation |
| BM25 beats hybrid on Hit@1/MRR | `docs/METHODOLOGY.md` 99-case table |
| 8-corpus generalizability | `docs/METHODOLOGY.md` cross-corpus summary |
| Contaminated cases removed | `eval/audit_contamination.py`, 2 of 101 |
| Determinism guarantee | `eval/test_determinism.py` |
| Miss taxonomy, 4 categories | `docs/METHODOLOGY.md` |

## Open questions before drafting
1. Publish under Thoughtworks Insights first (employer brand, 6 to 8 week editorial cycle) or
   dev.to first for speed and canonical-link the rest? Insights first is the credibility play.
2. How much hitgate to show. Risk: the post reads as a tool pitch. Mitigation: hitgate appears
   only as the source of numbers, never as a recommendation to install anything.
3. Length. Insights and InfoQ tolerate 2500 to 3500 words; the discriminability section deserves
   the most room.

## Citation discipline
Verify every external citation before drafting. The research pass returned arXiv IDs with
internally inconsistent dates. Independently confirmed so far: OpenAI Evals deprecated
2026-06-03, read-only 2026-10-31, shutdown 2026-11-30, official migration path to promptfoo.
