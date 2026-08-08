# Part 1, Sections 6 to 8 (draft)

> Draft 1, 2026-08-07. ~780 words. Runs after `part-1-section-5-draft.md`.

---

## 6. Publish the number that disagrees with you

The ablation in section 5 had a job: prove the evaluation set could detect a real change. It did
that.

It also half-refuted the retriever it was testing.

Look again at the 99-case table. BM25-only, a deliberately crippled single-channel mode, beats the
full hybrid design on Hit@1, 0.737 against 0.636, and on MRR, 0.803 against 0.784. Hybrid only wins
further down the ranking, at Hit@5, where it reaches 0.99 and is the only mode scoring 1.0 across
all three intent classes at once.

I built the hybrid pipeline believing it was better. The measurement says: better at one thing,
worse at another.

There are two ways to handle that moment. One is to report Hit@5, which flatters the design, and
stay quiet about Hit@1. This is extremely common and almost never deliberate. You pick the metric
that matches your intuition, and the intuition never gets tested.

The other is to narrow the claim until it is true.

The narrowed version: hybrid is the right default when what matters is whether the answer appears in
the top five, which is the case when results feed a context window rather than a human clicking one
link. If you need the single best hit, lexical matching is competitive here and considerably cheaper.

That is a smaller claim than I started with. It is also one I can defend with a number.

Part of the gap is the instrument, not the design, and I can say which part. Section 4 showed that
identifier-derived queries share tokens with the code they should find, which hands lexical matching
an advantage that has nothing to do with retrieval quality. So the eval set is skewed toward BM25 on
exactly the metric BM25 wins. I know the direction of that bias. I cannot cleanly separate its size
from the real effect, and pretending otherwise would be the same failure this article opened with.

This is not the only place measurement changed the design. The cross-encoder reranker was measured
to help code queries and to hurt prose queries, so it is scoped to code queries and triggered by a
score threshold, rather than applied everywhere because reranking is generally supposed to be good.
The default would have been slower and worse.

A gate that only ever agrees with you is not measuring anything. It is a mirror.

## 7. What this does not do

Being clear about the boundary is what keeps the method credible.

**It does not evaluate answers.** No faithfulness, no groundedness, no answer relevancy. Those need a
different layer, and tools like RAGAS and DeepEval do that layer well. If your failure is the model
inventing things, none of this touches it.

**It does not measure human-judged relevance.** The cases come from your corpus, not from a person
deciding what a good result looks like. It measures retrievability and regression. Nothing more.

**Absolute numbers do not travel.** A high score on a self-indexed corpus is optimistic by
construction. Comparing your number against a number from another project is meaningless.

**It degrades on corpora that do not describe themselves.** The high-confidence cases come from
docstrings and comments. A codebase with none falls back to identifier-derived queries, which
produces a weak, lexically-biased evaluation set. That is a real limitation, and worth checking
before you invest.

**It does not replace judged evaluation where the stakes need it.** For a medical or legal
retrieval system, label-free regression gating is a floor, not a substitute for expert review.

The point is not that labels are useless. It is that not having labels is a bad reason to have no
gate at all.

## 8. What comes next

Two things follow from here.

**Part 2 takes this to a real retrieval system end to end**, with results across eight corpora in
Python, TypeScript, React, and Next.js. The headline finding is one I did not expect: corpus
structure predicts retrieval performance more than language does. Codebases with clean module
boundaries score well regardless of language. One corpus, a homogeneous UI component layer where no
signal distinguishes sibling components, exposed a genuine ceiling the pipeline cannot pass.

**Part 3 generalizes the gate to agent outputs**, and lands the reference architecture: where the
gate sits, what a run costs per pull request, how to pick thresholds that do not flip on noise, and
what to do when it goes red.

If you take one thing from this part, take the cheapest one. Go break your retriever on purpose and
see whether your gate notices. You will know within an hour whether you have a gate or a mirror.
