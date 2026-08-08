# Your codebase decides how well retrieval works

*Part 2 of "Eval gates for delivery teams: label-free CI quality gates for retrieval and agents."*

What happened when I ran the same label-free gate across eight codebases in four languages, and why
the results tracked architecture rather than language.

> Draft 1, 2026-08-07. ~2,500 words. All numbers from `docs/METHODOLOGY.md`.
> Follows `part-1-draft.md`.

---

## 1. The obvious objection to Part 1

Part 1 made a case: you can gate retrieval regressions without labels, by mining evaluation cases
from your own corpus and gating on deltas against a frozen baseline. I showed the gate working on one
repository. My own.

The obvious objection is that a method validated on the codebase it was built for is not validated at
all. I tuned the retriever while looking at that corpus. Of course it scores well.

So I ran it on seven more.

## 2. The setup

Eight corpora. Python, TypeScript, React, Next.js, and one mixed. Sizes from 15 to 99 evaluation
cases. One of them is a well-known open source project I have never contributed to.

The rule I held to: **no per-corpus tuning.** Same retriever, same fusion, same chunkers, same
generator, same defaults. Point it at a repo, generate candidate cases, curate, run. If the method
needs hand-tuning per codebase, it is not a method, it is a hobby.

| Corpus | Language | Cases | Hit@5 | Hit@1 | MRR |
|---|---|---|---|---|---|
| hitgate (self-index) | Python | 99 | **1.0** | 0.636 | 0.784 |
| FastAPI | Python | 25 | **1.0** | 0.640 | 0.790 |
| ai-dev-toolkit / core | Python + TS | 20 | **1.0** | 0.850 | 0.925 |
| forge-space / mcp-gateway | TypeScript | 20 | **1.0** | 0.700 | 0.821 |
| portfolio / src | React / TS | 15 | **1.0** | 0.600 | 0.778 |
| homelab / homelab_manager | Python | 20 | 0.950 | 0.850 | 0.900 |
| Lucky / packages/backend | TypeScript | 21 | 0.905 | 0.714 | 0.810 |
| Criativaria / web-app | Next.js / TS | 27 | 0.741 | 0.593 | 0.660 |

Hit@5 = 1.0 on five of eight, and above 0.9 on seven of eight. The hybrid pipeline generalizes
without tuning.

That is the boring result. The interesting one is in the spread.

## 3. Language is not the variable

Look for a language pattern in that table and you will not find one.

Python appears at the top (ai-dev-toolkit, 0.850 Hit@1) and in the middle (hitgate, 0.636).
TypeScript appears near the top (forge-space, 0.700) and at the very bottom (Criativaria, 0.593).
React and Next.js sit at opposite ends of the ranking despite being nearly the same stack.

Sort by Hit@1 instead and a different pattern appears immediately. The strong corpora
(ai-dev-toolkit 0.850, homelab 0.850) have clean functional module boundaries: a file does one job
and its name says which job. The weak corpora (Criativaria 0.593, portfolio 0.600) are
same-layer collections where many files do very similar jobs.

**Corpus structure predicts retrieval performance more than language does.**

This is not a subtle effect. The gap between the best and worst corpus is 26 percentage points of
Hit@1, and it lines up with architecture almost perfectly.

It also reframes what a bad retrieval score means. My first instinct on a low number was always to go
tune the retriever. On at least two of these corpora, that instinct would have wasted a week.

## 4. Where the misses actually come from

To know whether the retriever was worth further investment, I classified every case that failed to
reach rank 1. At the 50-case snapshot of my own corpus, that was 22 cases out of 50.

The first finding was the one that mattered:

**None of the 22 were vocabulary gaps.** Every single one returned the correct file somewhere in the
top five. The retriever found the file. It just ranked something else above it.

That is a completely different problem from "search is broken", and it needs a completely different
response. Four patterns covered all 22 cases.

**Implementation versus entry point (9 cases).** The repo separates the module that implements a
behavior from the module that calls it. A query like "hybrid retrieval fusing BM25 and cosine with
reciprocal rank fusion" matches both. The CLI ranks first, the implementation second. Neither answer
is wrong. There is no signal in the query saying which architectural layer the asker wanted.

**Test and tooling files mirroring the code they exercise (7 cases).** The contamination auditor
classifies files, so it echoes the vocabulary of the indexer that classifies files. The history
plotter re-indexes the repo, so it echoes the builder. A query about indexing git commits ranks the
plotting script first and the actual indexer second. The core module wrote the behavior. The eval
module described it, often in plainer language, which is exactly what retrieval rewards.

**Adapter confusion (4 cases).** Two adapters both "expose retrieval as a callable tool." A query
describing that function cannot distinguish them.

**Definition versus use (2 cases).** A query about excluded directories ranks the function that
applies the exclusion list above the config file that declares it.

Every one of these is the same underlying shape: two files legitimately answer the question, and
nothing in the corpus says which is authoritative.

## 5. The fix that was not in the pipeline

There was one class of miss that behaved differently, and it is the most useful finding in this
article.

Two cases about the chunking module missed persistently, across every embedding mode and every
prefix configuration I tried. The queries used words like "passages", "vectorized", "fragments",
"declaration boundaries", and "line counts". None of those words appeared anywhere in the module's
docstring or function names. The dense channel had nothing to anchor to.

I fixed it by adding one sentence to a docstring:

> "Splits source files into smaller fragments (passages / segments) before they are embedded... at
> logical declaration boundaries... rather than slicing at arbitrary line counts."

Both cases went from MISS to rank 1. Nothing else regressed. Hit@5 moved from 0.913 to 1.0 on the
case set at the time.

I had spent considerably longer on embedding prefix experiments that moved nothing.

**When a miss is a vocabulary gap, the highest-leverage fix is in the corpus, not the pipeline.**
Adding plain-English description to the module is direct, self-documenting, and it improves the code
for humans at the same time. Prefix tricks and rerankers can compensate for missing vocabulary, but
they are working around a gap you could simply close.

The docstring is now true and retrievable. Those are the same property.

## 6. Knowing when to stop

The lowest score in the table is Criativaria at 0.741 Hit@5, and it is the most instructive corpus in
the set.

It is a Next.js UI component library. Almost everything in it lives at the same architectural layer.
Components share near-identical vocabulary: layout, SEO, chrome, effects, pickers. Three cases miss
entirely, falling outside the top five, and in each one the target component's distinguishing words
also appear across several sibling components.

There is no retriever tuning that fixes this, because the information required to rank one sibling
above another is not present in the corpus. The dense channel has no signal to prefer one layout
component over another layout component. Neither does BM25.

This is a genuine ceiling, and being able to name it is the point of doing the classification work in
section 4. The options are a cross-encoder reranker, which is the recommended path for homogeneous
component libraries and costs latency, or accepting that retrieval over this corpus will be
mediocre.

What you should not do is spend a sprint tuning fusion weights. The eval told me where the ceiling
was. Without the per-corpus breakdown I would have read 0.741 as "the retriever needs work" and been
wrong.

## 7. The bug you only find by benchmarking

One more result, because it is the kind of thing that justifies the exercise on its own.

Running the benchmark on the Lucky backend, the index came back with 237 code files. The project has
about 79.

Stryker, the JavaScript mutation testing tool, creates `.stryker-tmp/sandbox-*/` directories
containing full copies of the source tree. Every copy was being indexed. Top results were dominated
by paths like `.stryker-tmp/sandbox-wX56Wb/src/utils/prometheus.ts`.

The fix was one entry in the excluded-directories list. After it: 79 files, 343 chunks, clean
results.

Nobody would have noticed this from using the search. Results looked plausible. It took a benchmark
that expected specific files to surface for the duplication to become visible, and the fix applies to
any TypeScript project using Stryker.

Evaluation infrastructure finds infrastructure bugs. That is a second reason to build it, separate
from the gating.

## 8. What to take from this

Four things, in order of how much time they will save you.

1. **Before tuning the retriever, classify your misses.** If the correct file is already in the top
   five, you have a ranking problem, not a retrieval problem, and most pipeline tuning will not
   touch it.
2. **If the miss is a vocabulary gap, fix the source.** One honest docstring beats a week of
   embedding experiments, and it survives your next pipeline change.
3. **Expect your architecture to set your ceiling.** Codebases with clear layer separation retrieve
   well. Flat collections of similar components do not, in any language.
4. **Run the benchmark on a corpus you did not build.** It is the only way to find out which of your
   results were properties of the method and which were properties of your repo.

Part 3 takes the same gate shape to agent outputs, where the thing being compared is a trajectory
rather than a ranked list, and lands the full architecture: where the gate sits in CI, what a run
costs per pull request, how to pick thresholds that do not flip on noise, and what to do when it goes
red.

---

## Notes on the numbers

The eight-corpus table and the per-corpus breakdowns are from `docs/METHODOLOGY.md` in
[hitgate](https://github.com/LucasSantana-Dev/hitgate) and are reproducible with the commands there.

The miss taxonomy in section 4 was done at a 50-case snapshot of the self-indexed corpus, where
Hit@1 was 0.56. The case set later grew to 99. The four categories held; the counts are from the
50-case snapshot and are labeled as such to avoid mixing them with the 99-case figures used in
Part 1.
