# Part 1, Sections 1 to 4 (draft)

> Draft 1, 2026-08-07. ~1,050 words. Runs before `part-1-section-5-draft.md`.
> Mechanism details verified against `hitgate/generate.py`.

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
*metrics* are a solved problem. RAGAS and DeepEval will score faithfulness and answer relevancy with
no ground truth at all. What is not solved is reference-free *regression gating*. Every mainstream
tool still needs a curated set to establish the baseline it compares against. The metric is
label-free. The gate is not.

That is the gap this series is about.

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
