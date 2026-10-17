# How it works, and bringing your own retriever

## The problem

Building RAG systems is straightforward. Knowing whether a change made retrieval better or worse is
hard, especially with a small corpus and no production telemetry. You cannot A/B test with one user,
you cannot afford hand-labeled golden sets, and LLM judges are expensive and opaque.

hitgate solves one specific problem: detect retrieval regressions without labels, like a test suite
for ranking quality.

## What it does, and what it does not

- Proves whether retrieval improved or regressed between two runs.
- Works with zero labeled data. No golden set is required to start.
- Gates on measurable deltas: Hit@K, MRR, per-intent breakdown.
- Plugs into your retriever: point `--retriever` at any callable `(query, top, scope) -> [results]`.
- Does not measure absolute quality. Hit@5 near 1.0 on a self-indexed corpus is optimistic by design.
- Not a framework or hosted service. It is a harness you fork and customize.
- Not a maintained product. Personal tooling shared for the methodology.

How it differs from RAGAS, DeepEval and Braintrust: those gate answer quality (faithfulness,
relevancy) with labeled golden sets or LLM judges. hitgate gates retrieval ranking with no labels.
Different layer, complementary. Full comparison: [COMPARISONS.md](COMPARISONS.md).

## The bundled hybrid retriever

- Dense embeddings (`intfloat/multilingual-e5-small`) plus BM25 lexical search.
- Reciprocal Rank Fusion to combine both signals.
- Code-aware tokenizer: splits `camelCase` and `snake_case`, so "get user profile" matches `getUserProfile`.
- Language-aware chunking: Python via AST, TS/JS/Shell via regex, word-count fallback.
- Optional reranking: a cross-encoder scoped to code queries, with graceful fallback if unavailable.

It is the reference implementation the gate measures. You do not need it to use the gate.

## The eval gate

1. Run your retriever against a golden set of queries (20 to 99 JSON cases).
2. Measure Hit@1/3/5 and MRR: does the expected file rank in the top K?
3. Freeze a baseline when you like the results.
4. Gate future changes: CI exits 1 if any metric regresses by more than 5 points.

| Metric | Meaning |
|---|---|
| Hit@K | share of queries where the expected file appears in the top K results |
| Hit@5 | the regression-gated headline metric (tolerates ranking imprecision) |
| Hit@1 | strict perfect-ranking metric, useful for spotting misses |
| MRR | mean reciprocal rank, the average of `1/rank` across queries |

Self-indexed results are optimistic by construction. Point the gate at your own retriever for
numbers that mean something. Limits and miss taxonomy: [METHODOLOGY.md](METHODOLOGY.md).

## Bring your own retriever, in 4 steps

A retriever is any callable:

```python
retrieve(query: str, top: int, scope: str | None) -> Sequence[Mapping]
# Results ranked best-first; each a Mapping with at least "path" (optionally "start_line")
```

### 0. Bootstrap candidate golden cases (optional)

```bash
RAG_SOURCE_ROOTS="/path/to/corpus" python -m hitgate.generate \
    --output hitgate/candidates.jsonl \
    --min-confidence medium
```

Review and curate to remove vague queries or wrong expected paths.

### 1. Write golden cases

```jsonl
{"query": "how does pagination work", "expect_path_contains": "api/pagination.py", "expect_scope": "code"}
{"query": "rate limit config", "expect_path_contains": "config/limits.yaml", "expect_scope": "code"}
```

Aim for 20 to 50 cases mixing identifier lookups and paraphrased queries. Save as any `.jsonl`.

### 2. Run your retriever

```bash
hitgate-run \
    --retriever mypkg.myretriever:retrieve \
    --dataset   my_golden.jsonl \
    --label     baseline-v1
```

Writes `baseline-v1.json` in the current directory with Hit@1/3/5, MRR and a per-case breakdown.

### 3. Freeze the baseline

```bash
cp baseline-v1.json baseline.myproject.json
```

Edit `_note` to record the conditions: corpus, model, date. Commit it.

### 4. Gate future runs

```bash
hitgate-run --retriever mypkg.myretriever:retrieve --dataset my_golden.jsonl --label ci
hitgate-compare ci.json baseline.myproject.json
# Exits 1 if any gated metric regresses by more than 5 points
```

Drop-in CI: [`examples/retrieval-gate.yml`](../examples/retrieval-gate.yml).

### Diff two runs case by case

```bash
hitgate-diff baseline-v1.json ci.json
```
