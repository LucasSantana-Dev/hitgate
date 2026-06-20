# evidence-first-rag

[![eval-gate (advisory)](https://github.com/LucasSantana-Dev/evidence-first-rag/actions/workflows/eval.yml/badge.svg)](https://github.com/LucasSantana-Dev/evidence-first-rag/actions/workflows/eval.yml)

> **A pytest-style regression gate for retrieval quality** — plus the small hybrid
> retriever it was built to measure. Point it at *your* retriever and find out whether a
> change helped or hurt, when you have **no labeled data and no users to A/B against**.

**Status:** working · stable · single-author personal tooling, published for the
*methodology*. The adoptable part is the **harness**: a label-free, regression-gated quality
check for any retriever (`--retriever module:callable`). The bundled hybrid engine is just
the thing it measures.

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

# Run the eval gate (bundled retriever)
RAG_RERANK_AUTO=off python eval/run.py --label demo

# ...or point the SAME gate at YOUR retriever — any callable (query, top, scope) -> [{"path": ...}]
python eval/run.py --retriever eval.example_external_retriever:retrieve --label mine
```

That eval indexes the repo's own source and scores 50 golden cases against it — so
**you can reproduce the number below yourself**, no private data required.

## Results (honest, self-indexed demo)

| Metric | Value |
|---|---|
| **Hit@5** (code scope, pure hybrid) — *the regression-gated headline* | **1.0** |
| Hit@1 | 0.56 |
| MRR | 0.741 |
| Corpus | this repo, self-indexed · 50 cases (25 identifier + 25 paraphrase) |

28 of 50 cases hit at rank 1; the misses are left in on purpose. Inflating a benchmark by
quietly dropping the cases it fails is the first thing this project refuses to do — see
[DECISIONS.md](./DECISIONS.md); measured before/after deltas are in
[CHANGELOG.md](./CHANGELOG.md). An honest ablation — where **BM25-only wins Hit@1**
(0.522) while **hybrid wins Hit@5** (1.0, all three intent classes covered) — is
walked through in [docs/METHODOLOGY.md](./docs/METHODOLOGY.md).

Because the demo indexes **this repo itself**, the corpus grows as the repo does, so
Hit@1 and MRR drift over time — adding a file can demote a borderline case. That's why
**Hit@5 is the number under regression gate** (`eval/check.sh`, ±5pp). The drift is the
honest behavior of a self-indexing benchmark, not noise swept under a frozen number.

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
- **Eval (the point)** — `eval/run.py` reports Hit@K/MRR for *any* retriever via
  `--retriever`; `eval/check.sh` gates a run against a frozen baseline (±5pp).
- **Golden set generator** — `eval/generate.py` bootstraps candidate cases from your corpus
  structure (docstrings, symbol names) with zero dependencies. LLM paraphrase generation is
  opt-in via `--llm`. Output feeds directly into `eval/run.py --dataset`.

## Use it on your own retriever

The harness doesn't care whose retriever it's measuring. A retriever is any callable:

```python
retrieve(query: str, top: int, scope: str | None) -> Sequence[Mapping]
# results ranked best-first; each a mapping with at least "path" (optionally "start_line")
```

Point the gate at yours with `--retriever module.path:callable`:

```bash
python eval/run.py --retriever mypkg.myretriever:retrieve --label mine
```

A runnable, dependency-free example — a deliberately dumb keyword matcher — is in
[`eval/example_external_retriever.py`](./eval/example_external_retriever.py). Ecosystem
wrappers (LangChain / LlamaIndex) live under [`adapters/`](./adapters/README.md). Bring your
own retriever and corpus; keep the measurement discipline.

### Bring your own corpus — 4-step quickstart

**0. Bootstrap candidate cases from your corpus (optional):**
```bash
RAG_SOURCE_ROOTS="/path/to/your/corpus" python eval/generate.py \
    --output eval/candidates.jsonl \
    --min-confidence medium

# LLM-enhanced (identifier + paraphrase per chunk, no extra package needed):
OPENAI_API_KEY=sk-... RAG_SOURCE_ROOTS="/path/to/your/corpus" \
    python eval/generate.py --llm --output eval/candidates.jsonl
```
Review and curate `eval/candidates.jsonl` — delete cases where the query is too vague
or the expected file is wrong — then use it as your golden set below.

**1. Write golden cases** — each is a JSON object with three fields:
```jsonl
{"query": "what handles pagination in the API", "expect_path_contains": "api/pagination.py", "expect_scope": "code"}
{"query": "where are rate limits configured",    "expect_path_contains": "config/limits.yaml", "expect_scope": "code"}
```
`expect_path_contains` is a substring of the expected result's path (file name is usually enough).
Aim for 20–50 cases across a mix of identifier lookups and paraphrase queries. Save as any `.jsonl`.

**2. Run your retriever against the cases:**
```bash
python eval/run.py \
    --retriever mypkg.myretriever:retrieve \
    --dataset   my_golden.jsonl \
    --label     baseline-v1
# writes eval/baseline-v1.json with hit@1/hit@3/hit@5/mrr + per_case breakdown
```

**3. Freeze the baseline:**
```bash
cp eval/baseline-v1.json eval/baseline.my-project.json
# edit _note to record conditions: corpus, model, date
```

**4. Gate future runs with check.sh:**
```bash
# eval/check.sh already reads BASELINE_FILE env var
BASELINE_FILE=eval/baseline.my-project.json \
RAG_SOURCE_ROOTS="/path/to/your/corpus" \
python eval/run.py --retriever mypkg.myretriever:retrieve --dataset my_golden.jsonl --label ci
bash eval/check.sh eval/ci.json eval/baseline.my-project.json
# exits 1 if any metric regresses by more than 5pp
```

To diff two runs case-by-case: `python eval/diff.py eval/baseline-v1.json eval/ci.json`.

## What to adopt (and what to skip)

**Adopt the harness.** The reusable thing here is `eval/` — the label-free, regression-gated
quality check and the `--retriever` interface. The bundled hybrid engine is a reference
implementation, not the product. What this is **not**:

- **Not a framework or a hosted service** — no plugin marketplace, no SaaS. Fork the harness;
  the retriever is swappable by design.
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
