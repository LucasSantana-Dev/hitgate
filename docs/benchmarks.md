# Benchmarks

Every number here came out of a `hitgate-run` invocation you can repeat. Method, ablations and the
miss taxonomy live in [METHODOLOGY.md](METHODOLOGY.md). Read the caveats first: these are
self-indexed or auto-mined sets, so they are optimistic by construction. Use them to compare two
configurations, not to certify absolute quality.

## Self-indexed demo (reproducible)

99 golden cases over this repository, pure retrieval (`RAG_RERANK_AUTO=off`), measured 2026-10-17
on commit `4f289f1` plus this documentation change:

| Rank mode | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---|---|
| BM25 only | **0.747** | 0.848 | 0.909 | **0.804** |
| Dense only | 0.646 | 0.869 | 0.899 | 0.744 |
| **Hybrid (BM25 + dense + RRF)** | 0.616 | **0.919** | **0.990** | 0.765 |

Reproduce:

```bash
RAG_SOURCE_ROOTS="$PWD" python -m ragcore.build
for m in bm25 dense hybrid; do
  RAG_RANK_MODE=$m RAG_RERANK_AUTO=off python -m hitgate.run \
    --dataset hitgate/golden.demo.jsonl --label abl-$m
done
```

Reading the table:

- Hybrid is the only mode that keeps Hit@5 near 1.0. Single-channel modes lose 8 to 9 points.
- BM25 alone wins Hit@1 and MRR here. The corpus is identifier heavy, so lexical match is strong.
  The measurement contradicts the design in places, and that is published on purpose.
- Hit@1 moves by a couple of points whenever files are added to the corpus (it was 0.636 on an
  earlier snapshot). Hit@5 is the gated metric because it tolerates that drift.

Per-intent breakdown for the hybrid run: indexing 22 cases (Hit@5 1.000), infrastructure 47
(1.000), retrieval 30 (0.967).

## External corpora (zero tuning)

Same tokenizer and settings on every corpus, golden sets written for each one:

| Corpus | Language | n | Hit@5 | Hit@1 | MRR |
|---|---|---|---|---|---|
| FastAPI v0.115 | Python | 25 | **1.0** | 0.64 | 0.79 |
| portfolio / src | React/TS | 15 | **1.0** | 0.60 | 0.778 |
| ai-dev-toolkit / packages/core | Python + TS | 20 | **1.0** | 0.85 | 0.925 |
| homelab / homelab_manager | Python | 20 | 0.950 | 0.85 | 0.900 |
| Lucky / packages/backend | TypeScript | 21 | 0.905 | 0.71 | 0.810 |
| Criativaria / web-app | Next.js/TS | 27 | 0.741 | 0.59 | 0.660 |

Finding: corpus module clarity predicts Hit@1 better than language or size. Clean functional
boundaries reach 0.85. Same-layer UI components sit near 0.59.

Selection bias: FastAPI is third-party, and the others are the author's own repositories. The full
per-corpus write-up is in [METHODOLOGY.md](METHODOLOGY.md#external-corpus-benchmarks). A broader
70-repository auto-generated sweep is in [portfolio-benchmark.md](portfolio-benchmark.md) and
[SWEEP.md](SWEEP.md), with its own warning that auto-mined Hit@5 saturates.

## Reranking

On the 50-case set, forced global reranking drops Hit@5 from 1.0 to 0.96, and the auto-trigger
(margin 0.015) keeps Hit@5 at 1.0 while adding 6 points of Hit@1. The Pareto table across two
cross-encoders and the margin sweep are in [METHODOLOGY.md](METHODOLOGY.md).

## Production-corpus context (not a before/after)

On a private 7,800-chunk corpus (notes, ADRs, plans and five code repositories), the sibling engine
measured Hit@5 0.587 on a 46-case frozen holdout, and 0.86 on the 43 memory-scope cases of its
training set. Those are two different slices of a different corpus, not an improvement of one
metric. The eval sets are private and cannot be distributed.
