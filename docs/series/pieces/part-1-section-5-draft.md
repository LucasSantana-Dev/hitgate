# Part 1, Section 5 (draft): Prove the gate can fail

> Draft 2, 2026-08-07. ~600 words. All numbers from `docs/METHODOLOGY.md`.

---

## Prove the gate can fail

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
