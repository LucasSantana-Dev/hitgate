# A gate you have never seen fail is not a gate

*Part 1 of "Eval gates for delivery teams: label-free CI quality gates for retrieval and agents."*

How to build a regression gate for LLM retrieval without a labeled golden set, and how to prove the
gate actually works before you trust it.

> Draft, assembled 2026-08-07. Source pieces in `pieces/`. Edit THIS file from now on.

---

## 1. My gate reported a perfect score and meant nothing

I built a regression gate for a retrieval system. It ran on every change, compared against a frozen
baseline, and reported Hit@5 = 1.0.

The score was real. I had not fabricated it or tuned to it. And it was worthless, because the
evaluation set behind it was too small to tell two very different retrievers apart. The gate could
not have gone red. It was reporting, not gating.

I had done what the guides say: pick a metric, build a small evaluation set, wire it into CI, gate
on the number. Every one of those steps was fine. The problem sat underneath all of them, and no
output from the gate would ever have revealed it.

What revealed it was running an ablation: deliberately crippling the retriever to see whether the
gate noticed. It did not. Two configurations with completely different failure modes came back with
identical scores.

Fixing that took the evaluation set from 24 cases to 99. The numbers are in section 5.

## 2. Why "build a golden set first" stalls teams

Ask how to evaluate an LLM system and the answer is a labeled golden set: queries paired with
correct answers, written or reviewed by a human.

It is good advice and it stops most teams cold.

The cost lands before any value. Someone writes a few hundred labeled examples before the first
regression is ever caught. That work is hard to justify against feature work, so it slips, and the
system ships with no gate at all.

Then the sets rot. The corpus moves. Cases quietly become unwinnable, because the answer they expect
is no longer indexed. Nobody notices, because a failing case looks the same as a hard case.

And the advice assumes a scale most teams do not have. A/B testing needs traffic. Production
telemetry needs production. On an internal tool with forty users, you have neither.

One clarification, because this is where the conversation usually gets muddled. Reference-free
*metrics* are a solved problem. RAGAS and DeepEval both ship metrics that need no ground truth:
faithfulness scores the answer against the retrieved context, and answer relevancy scores it against
the question. Neither needs an expected answer.

But a metric is not a gate. To detect a regression you need a *fixed set of inputs* to re-run
against a frozen baseline, and that is where labels sneak back in. You have two ways to get that
set: curate one by hand, or replay real production traffic. RAGAS is explicit that you can run its
reference-free metrics over collected production traces, and if you have that traffic, that is a
good option.

If you do not have it, you are back to hand-curation, which is where most teams stall. The metric
became label-free. The gate did not.

That is the gap this series is about: a fixed input set that costs neither annotation budget nor
production traffic.

## 3. Stop scoring. Start diffing.

The reframe is small and it changes what you need.

Stop asking "is this output good?" Start asking "did this change move anything, and is the movement
bigger than my noise?"

The first question needs ground truth. The second does not. It needs a baseline you froze earlier
and the ability to re-run against it.

This is how test suites already work. A test does not assert that your function is good. It asserts
that it still does what it did yesterday. Almost all of a test suite's value is regression
detection, and regression detection never needed an absolute standard of quality.

So gate on deltas. Never on absolute scores.

Absolute scores from a label-free set are close to meaningless anyway, and I want to be blunt about
that. When your evaluation set is derived from your own corpus, a high score is optimistic by
construction. It does not mean retrieval is good. Compare that number across two projects and you
learn nothing.

The same number compared against last week, on the same corpus, with the same pipeline, tells you
something real: it moved, or it did not.

The honest framing to carry through the rest of this series:

> Label-free evaluation measures retrievability and regression. It does not measure human-judged
> relevance.

Claim more than that and the whole approach deserves the skepticism it gets.

## 4. Where the cases come from when nobody labels them

If you are not writing labeled pairs by hand, the corpus has to produce them.

For code retrieval it already does. Every chunk that gets indexed carries natural-language
descriptions of itself: docstrings, JSDoc blocks, leading comments, and the symbol name. Those are
queries someone already wrote. The file the chunk came from is the expected result. The pair exists
before you do any work.

The generator walks the source with the same chunker the index uses, and emits a query per chunk at
one of three confidence tiers:

- **High**: the chunk has a docstring of 25 characters or more. Use it verbatim.
- **Medium**: no docstring, so build the query from the symbol name split into words, plus the first
  comment. `chunk_python` becomes "chunk python". `getUserProfile` becomes "get user profile".
- **Low**: a module-level chunk with neither. Fall back to the first substantial line.

Intent is inferred from the filename, so results can be broken out by category later rather than
hidden in one average.

Two things matter more than the mechanics.

**These are candidates, not a golden set.** The generator produces a file you curate. Curation is
much cheaper than authoring, which is the entire point, but it is not zero. Low-confidence cases in
particular are usually noise and should be dropped.

**The tiers are not equally useful, and the reason is worth understanding.** A medium-confidence
query is built from the identifier, so it shares tokens with the code it is supposed to find. Lexical
matching wins those almost for free. A high-confidence query is a human sentence describing behavior,
and it often shares no tokens with the implementation at all. Those are the cases that actually test
whether semantic retrieval works.

A set skewed toward identifier-derived queries will flatter a lexical retriever and tell you very
little. This is not hypothetical. It shows up directly in the ablation numbers in section 5, where
the lexical-only mode beats the full hybrid design on the top-one metric.

Which raises the question the rest of this article is about. You now have an evaluation set that
cost you an afternoon instead of a month, and a gate that fires on deltas instead of absolutes.

How do you know it works?

## 5. Prove the gate can fail

An eval gate is an instrument. Instruments get calibrated before you trust them. Evals almost never do.

You already accept this rule elsewhere. You do not trust a test suite because it is green. You trust
it because you once broke the code and watched it go red. Ask your eval gate the same question:

**If retrieval genuinely got worse, would this gate notice?**

If you cannot answer with a number, the gate is not protecting you. It prints a reassuring number on
every pull request. That is worse than no gate, because it turns an open question into false confidence.

### The procedure

Break something that must hurt. Check that the gate reacts.

In a hybrid retriever this is easy. The design premise is that dense embeddings and lexical BM25
cover each other's weak cases. So turn off one channel at a time. If fusion is worth its complexity,
the crippled modes must score worse. If they do not, either the design is not earning its keep or the
eval cannot see the difference. Both are worth knowing.

```bash
RAG_SOURCE_ROOTS="$PWD" python -m ragcore.build
RAG_RANK_MODE=bm25   RAG_RERANK_AUTO=off python -m hitgate.run --dataset hitgate/golden.demo.jsonl --label abl-bm25
RAG_RANK_MODE=dense  RAG_RERANK_AUTO=off python -m hitgate.run --dataset hitgate/golden.demo.jsonl --label abl-dense
RAG_RANK_MODE=hybrid RAG_RERANK_AUTO=off python -m hitgate.run --dataset hitgate/golden.demo.jsonl --label abl-hybrid
```

Then set a bar. An ablation must move the metric by at least X for the eval set to count as working.

### My own gate, failing this test

An early version had 24 cases:

| Rank mode | Hit@1 | Hit@5 | MRR |
|---|---|---|---|
| BM25-only *(23-case)* | 0.522 | 0.826 | 0.639 |
| dense-only *(23-case)* | 0.478 | 0.826 | 0.617 |
| hybrid *(24-case)* | 0.458 | **1.0** | 0.680 |

Both crippled modes scored **exactly 0.826**. Two retrievers with different failure modes, one
number. The ablation proved nothing. A set that cannot separate two deliberately broken configs
cannot catch a subtle real regression either.

The gate did not say so. It reported Hit@5 = 1.0 and looked healthy.

The fix was not a better metric. It was more cases: 12, 17, 23, 24, 59, 101, then 99 after removing
two broken ones. At 99 cases:

| Rank mode | Hit@1 | Hit@5 | MRR |
|---|---|---|---|
| BM25-only | **0.737** | 0.909 | **0.803** |
| dense-only | 0.667 | 0.929 | 0.764 |
| **hybrid** | 0.636 | **0.99** | 0.784 |

Dense-only now drops Hit@5 by **6.1pp**. BM25-only by **8.1pp**. Both clear a 5pp bar. The set can
detect a real change, and I can prove it.

Only now does a green gate mean anything.

### First, kill the noise

A delta only means something if you know how much the number moves when nothing changed. Two honest
options:

1. **Make the eval deterministic.** Same query, same corpus, same ordering, every run. Then any delta
   comes from your change and you need no statistics. Assert it in a test, so the build fails if
   ordering drifts.
2. **Measure the variance.** If something is genuinely stochastic, run the baseline against itself N
   times and set the gate outside the spread.

Most teams do neither. They run once, see movement, call it signal. If your pipeline is
deterministic, option 1 is a few hours and deletes the whole problem.

### The catch

This proves the gate detects *a* change. It does not prove it detects *the* change you care about.
Treat the ablation as a floor, not a certificate.

It rules out one specific failure: a gate that was never able to go red. That failure is common,
invisible, and cheap to check.

**A gate you have never seen fail is not a gate.**

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

---

## Sources (verified 2026-08-07)

External claims in this article are limited to what RAGAS and DeepEval do. Everything else is
measured in [hitgate](https://github.com/LucasSantana-Dev/hitgate) and reproducible with the
commands shown.

- RAGAS reference-free evaluation, including over collected production traces:
  [Langfuse, Evaluation of RAG pipelines with Ragas](https://langfuse.com/guides/cookbook/evaluation_of_rag_with_ragas)
- RAGAS original paper: [RAGAS: Automated Evaluation of Retrieval Augmented Generation](https://arxiv.org/html/2309.15217v1)
- DeepEval referenceless metrics (`AnswerRelevancyMetric` needs input plus actual output;
  `FaithfulnessMetric` needs actual output plus retrieval context):
  [DeepEval docs, Faithfulness](https://deepeval.com/docs/metrics-faithfulness) and
  [Metrics introduction](https://deepeval.com/docs/metrics-introduction)
