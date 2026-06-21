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
pip install -e ".[hybrid]"   # harness core is dependency-free; [hybrid] adds the bundled retriever

# Index this repo into a local ./.rag-index/ (the tool indexes itself)
RAG_SOURCE_ROOTS="$PWD" python -m ragcore.build

# Ask it something
RAG_SOURCE_ROOTS="$PWD" python -m ragcore.query --scope code "how does the reranker fall back"

# Run the eval gate (bundled retriever)
RAG_RERANK_AUTO=off python -m hitgate.run --label demo

# ...or point the SAME gate at YOUR retriever — any callable (query, top, scope) -> [{"path": ...}]
python -m hitgate.run --retriever hitgate.example_external_retriever:retrieve --label mine
```

That eval indexes the repo's own source and scores 50 golden cases against it — so
**you can reproduce the number below yourself**, no private data required.

## Results

### Self-indexed demo (reproducible)

| Metric | Value |
|---|---|
| **Hit@5** (code scope, pure hybrid) — *the regression-gated headline* | **1.0** |
| Hit@1 | 0.663 |
| MRR | 0.800 |
| Corpus | this repo, self-indexed · 101 cases |

67 of 101 cases hit at rank 1; the misses are left in on purpose. Inflating a benchmark by
quietly dropping the cases it fails is the first thing this project refuses to do — see
[DECISIONS.md](./DECISIONS.md); measured before/after deltas are in
[CHANGELOG.md](./CHANGELOG.md). An honest ablation — where **BM25-only wins Hit@1**
(0.522) while **hybrid wins Hit@5** (1.0) — is walked through in
[docs/METHODOLOGY.md](./docs/METHODOLOGY.md).

Because the demo indexes **this repo itself**, the corpus grows as the repo does, so
Hit@1 and MRR drift over time — adding a file can demote a borderline case. That's why
**Hit@5 is the number under regression gate** (`hitgate/check.sh`, ±5pp). The drift is the
honest behavior of a self-indexing benchmark, not noise swept under a frozen number.

### External corpus benchmarks

The same retriever — zero tuning, same `hitgate/run.py` pipeline — measured against 7 other
codebases with no corpus-specific configuration:

| Corpus | Language | n | Hit@5 | Hit@1 | MRR |
|---|---|---|---|---|---|
| FastAPI v0.115 | Python | 25 | **1.0** | 0.64 | 0.79 |
| forge-space / mcp-gateway | TypeScript | 20 | **1.0** | 0.70 | 0.821 |
| portfolio / src | React/TS | 15 | **1.0** | 0.60 | 0.778 |
| ai-dev-toolkit / packages/core | Python + TS | 20 | **1.0** | 0.85 | 0.925 |
| homelab / homelab\_manager | Python | 20 | 0.950 | 0.85 | 0.900 |
| Lucky / packages/backend | TypeScript | 21 | 0.905 | 0.71 | 0.810 |
| Criativaria / web-app | Next.js/TS | 27 | 0.741 | 0.59 | 0.660 |

Hit@5=1.0 on four of seven corpora. The two lowest-performing corpora have structural
causes: Lucky has one Category B drift miss (Prometheus registry vs middleware, identical
vocabulary); Criativaria is a homogeneous Next.js component library where sibling components
are lexically indistinguishable — a genuine retrieval ceiling, not a tuning problem.

The finding that matters: **corpus module clarity predicts Hit@1 better than language or
size.** Clean functional boundaries (homelab, ADT) → 0.85. Same-layer UI components
(portfolio, Criativaria) → 0.59–0.60. Python vs TypeScript is not the variable.

Full methodology, miss taxonomy, and reproduce commands: [docs/METHODOLOGY.md](./docs/METHODOLOGY.md).

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
- **Eval (the point)** — `hitgate/run.py` reports Hit@K/MRR for *any* retriever via
  `--retriever`; `hitgate/check.sh` gates a run against a frozen baseline (±5pp).
- **Golden set generator** — `hitgate/generate.py` bootstraps candidate cases from your corpus
  structure (docstrings, symbol names) with zero dependencies. LLM paraphrase generation is
  opt-in via `--llm`. Output feeds directly into `hitgate/run.py --dataset`.

## Use it on your own retriever

The harness doesn't care whose retriever it's measuring. A retriever is any callable:

```python
retrieve(query: str, top: int, scope: str | None) -> Sequence[Mapping]
# results ranked best-first; each a mapping with at least "path" (optionally "start_line")
```

Point the gate at yours with `--retriever module.path:callable`:

```bash
python -m hitgate.run --retriever mypkg.myretriever:retrieve --label mine
```

A runnable, dependency-free example — a deliberately dumb keyword matcher — is in
[`hitgate/example_external_retriever.py`](./hitgate/example_external_retriever.py). Ecosystem
wrappers (LangChain / LlamaIndex) live under [`adapters/`](./adapters/README.md). Bring your
own retriever and corpus; keep the measurement discipline.

### Bring your own corpus — 4-step quickstart

**0. Bootstrap candidate cases from your corpus (optional):**
```bash
RAG_SOURCE_ROOTS="/path/to/your/corpus" python -m hitgate.generate \
    --output hitgate/candidates.jsonl \
    --min-confidence medium

# LLM-enhanced (identifier + paraphrase per chunk, no extra package needed):
OPENAI_API_KEY=sk-... RAG_SOURCE_ROOTS="/path/to/your/corpus" \
    python -m hitgate.generate --llm --output hitgate/candidates.jsonl
```
Review and curate `hitgate/candidates.jsonl` — delete cases where the query is too vague
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
python -m hitgate.run \
    --retriever mypkg.myretriever:retrieve \
    --dataset   my_golden.jsonl \
    --label     baseline-v1
# writes hitgate/baseline-v1.json with hit@1/hit@3/hit@5/mrr + per_case breakdown
```

**3. Freeze the baseline:**
```bash
cp hitgate/baseline-v1.json hitgate/baseline.my-project.json
# edit _note to record conditions: corpus, model, date
```

**4. Gate future runs with check.sh:**
```bash
# hitgate/check.sh already reads BASELINE_FILE env var
BASELINE_FILE=hitgate/baseline.my-project.json \
RAG_SOURCE_ROOTS="/path/to/your/corpus" \
python -m hitgate.run --retriever mypkg.myretriever:retrieve --dataset my_golden.jsonl --label ci
bash hitgate/check.sh hitgate/ci.json hitgate/baseline.my-project.json
# exits 1 if any metric regresses by more than 5pp
```

To diff two runs case-by-case: `python -m hitgate.diff hitgate/baseline-v1.json hitgate/ci.json`.

## What to adopt (and what to skip)

**Adopt the harness.** The reusable thing here is `hitgate/` — the label-free, regression-gated
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
