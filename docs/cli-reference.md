# CLI reference

After `pip install hitgate`, these commands are on your `$PATH`. Each also works as
`python -m <module>` (for example `python -m hitgate.run --label demo`).

## Indexing

**`rag-build`**: build a searchable index from source code and docs.

```bash
RAG_SOURCE_ROOTS="/path/to/corpus" rag-build
```

- `--incremental FILES`: reindex only specific files (for example `--incremental src/core.py docs/api.md`)
- `--no-code`: skip source code, index docs only

**`rag-query QUERY`**: search the indexed corpus.

```bash
rag-query "how does pagination work" --top 5 --format json
```

- `--top K` (default 5): return the top K results
- `--scope TYPE`: filter by source type (for example `--scope code` or `--scope docs`)
- `--rerank {on|off|auto}` (default `auto`): cross-encoder reranking
- `--format {text|json}`: output format

## Eval gate

**`hitgate-run`**: run the gate on a golden set and measure Hit@K and MRR.

```bash
hitgate-run --dataset eval/golden.jsonl --label baseline
```

- `--top K` (default 5): measure up to the top K
- `--label NAME` (default `baseline`): label for the output file
- `--dataset PATH`: golden set (JSONL)
- `--retriever MODULE:FUNC`: custom retriever (omit to use the bundled hybrid one)
- `--rerank`: force cross-encoder reranking (bundled retriever only)
- `--auto-rerank`: auto-trigger reranking on weak or ambiguous queries
- `--verbose`: show per-case details

**`hitgate-init [ROOT]`**: scaffold a label-free golden set from a corpus.

```bash
hitgate-init /path/to/corpus --output eval/golden.jsonl
```

- `--output PATH` (default `eval/golden.jsonl`): where to write the golden set
- `--min-confidence {high|medium|low}` (default `medium`): heuristic confidence threshold
- `--limit N` (default 0, unlimited): cap the number of candidate cases

**`hitgate-demo [ROOT]`**: one-shot demo. Build the index, mine cases, run the gate, print a verdict.

```bash
hitgate-demo /path/to/corpus --limit 12
```

- `--limit N` (default 12): number of golden cases to mine

## Analysis

**`hitgate-generate`**: mine candidate golden cases from a corpus (auto-generated, needs curation).

```bash
hitgate-generate --output candidates.jsonl --min-confidence medium
```

- `--output PATH` (default `hitgate/candidates.jsonl`): where to write candidates
- `--existing JSONL`: skip files already in an existing golden set
- `--min-confidence {high|medium|low}` (default `medium`): confidence threshold
- `--llm`: use an LLM to paraphrase queries (requires `OPENAI_API_KEY`)
- `--limit N`: cap total output cases

**`hitgate-compare CURRENT.json BASELINE.json [TOL_PP]`**: compare a run to a frozen baseline.
Exits 1 if any gated metric regresses by more than `TOL_PP` points (default 5).

**`hitgate-diff BASELINE.json HEAD.json`**: diff two eval result files case by case.

```bash
hitgate-diff eval/baseline.json eval/ci.json
```

- `--quiet`: summary line only, no per-case detail

**`hitgate-audit-contamination`**: check a golden set for leakage (eval queries that appear verbatim in the corpus).

```bash
hitgate-audit-contamination --dataset eval/golden.jsonl
```

- `--dataset PATH` (default `eval/golden.jsonl`): golden set to audit

## Configuration

The bundled retriever reads `RAG_*` environment variables. See [`ragcore/config.py`](../ragcore/config.py).
The ones you will touch most:

| Variable | Meaning |
|---|---|
| `RAG_SOURCE_ROOTS` | corpus roots to index |
| `RAG_INDEX_DIR` | where the SQLite index lives |
| `RAG_RANK_MODE` | `hybrid` (default), `bm25` or `dense` |
| `RAG_RERANK_AUTO` | `on` or `off`; auto-trigger the cross-encoder on weak queries |
