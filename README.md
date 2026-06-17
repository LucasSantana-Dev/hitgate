# evidence-first-rag

[![eval-gate (advisory)](https://github.com/LucasSantana-Dev/evidence-first-rag/actions/workflows/eval.yml/badge.svg)](https://github.com/LucasSantana-Dev/evidence-first-rag/actions/workflows/eval.yml)

> A small, portable **hybrid retrieval engine + evaluation harness** — and the
> measurement discipline that keeps it honest. Extracted from a personal AI-assistant
> memory index and decoupled from any specific tool, so it runs anywhere on any
> source tree.

**Status:** working · stable · single-author personal tooling, published for the
*methodology*. The interesting part isn't the retriever — it's how you tell whether
a change to it helped, when you have **no labeled data and no users to A/B against**.

---

## Why this exists

Building RAG is easy; *knowing whether a change made it better or worse* is the hard
part. With a small corpus and a single user you have none of the production crutches —
no click logs, no A/B traffic, no annotation budget. This repo is one answer: treat
retrieval quality as a **measurable, regression-gated property**, like a test suite,
and be ruthlessly honest about what the numbers do and don't prove.

## Quickstart (reproducible in ~10 seconds)

```bash
pip install sentence-transformers rank-bm25 numpy

# Index this repo into a local ./.rag-index/ (the tool indexes itself)
RAG_SOURCE_ROOTS="$PWD" python ragcore/build.py

# Ask it something
RAG_SOURCE_ROOTS="$PWD" python ragcore/query.py --scope code "how does the reranker fall back"

# Run the eval gate
RAG_RERANK_AUTO=off python eval/run.py --label demo
```

That eval indexes the repo's own source and scores 12 golden cases against it — so
**you can reproduce the number below yourself**, no private data required.

## Results (honest, self-indexed demo)

| Metric | Value |
|---|---|
| **Hit@5** (code scope, pure hybrid) — *the regression-gated headline* | **0.833** |
| Hit@1 | 0.667 |
| MRR | 0.75 |
| Corpus | this repo, self-indexed (code files; counts drift as the repo grows) |

8 of 12 cases hit at rank 1; the misses are left in on purpose (a couple of
`config.py` queries lose to `build.py`). Inflating a benchmark by quietly dropping
the cases it fails is the first thing this project refuses to do — see
[DECISIONS.md](./DECISIONS.md); measured before/after deltas are in
[CHANGELOG.md](./CHANGELOG.md). An honest ablation — where plain **BM25-only actually
edges hybrid** on this small demo — is walked through in
[docs/METHODOLOGY.md](./docs/METHODOLOGY.md).

Because the demo indexes **this repo itself**, the corpus grows as the repo does, so
the exact counts and Hit@1 drift over time — adding a file can demote a borderline
case. That's why **Hit@5 is the number under regression gate** (`eval/check.sh`, ±5pp);
it has held at 0.833 across these additions. The drift is the honest behavior of a
self-indexing benchmark, not noise swept under a frozen number.

## How it works

- **Hybrid retrieval** — dense embeddings (`intfloat/multilingual-e5-small`) + lexical
  BM25, fused with Reciprocal Rank Fusion. A code-aware tokenizer splits identifiers
  into `camelCase`/`snake_case` subtokens so "get user profile" matches `getUserProfile`.
- **Selective reranking** (optional) — a cross-encoder reranker that, when enabled, is
  scoped to code-scope queries only (it was measured to *help* code and *regress*
  prose), with graceful fallback to the fused ranking if the model isn't present.
- **Language-aware chunking** — Python by AST symbol, TS/JS/Shell by regex, with a
  word-count fallback.
- **Config by env var** — zero-setup defaults (`RAG_*`); see [`ragcore/config.py`](./ragcore/config.py).
- **Eval** — `eval/run.py` reports Hit@K/MRR; `eval/check.sh` gates a run against a
  frozen baseline.

## What this is NOT

- **Not a framework or a product** — no plugin API, no hosted service. The value is
  the approach; fork the harness, not the wiring.
- **Not state-of-the-art retrieval research** — a pragmatic single-user system that
  knows its own ceiling and stops there.
- **Not a maintained project** — a solo operator's personal tool, shared for the
  methodology. Issues and PRs are welcome but may not be triaged; expect best-effort,
  no SLA. The eval workflow is an *advisory* gate (it proves the numbers reproduce), not
  a support promise.

Other conventional repo furniture — `CONTRIBUTING`, issue templates, a badge wall — is
**deliberately** omitted, not unfinished. [DECISIONS.md](./DECISIONS.md) records what's
left out on purpose and the trigger that would reopen each.

## Extending

The core indexes code + docs + commits and nothing else, on purpose. Tool-specific
sources (assistant transcripts, code-graphs, other memory stores) plug in as opt-in
adapters — see [`adapters/README.md`](./adapters/README.md).

## Where this could go

Candidate experiments — each gated on a measured win, none promised — are written up in
[ROADMAP.md](./ROADMAP.md). They're directions, not commitments.

## License

MIT — see [LICENSE](./LICENSE). Use the methodology freely.
