# Adapters — extension points

The core (`ragcore/`) is deliberately **vendor-neutral and dependency-light**: it
indexes source code, markdown docs, and git commits from any set of roots, and
nothing more. Anything tied to a specific tool, host, or data store lives here as
an *opt-in* adapter so the core never depends on it.

## The source-adapter contract

A source adapter contributes rows to the index. The simplest form is a function
that yields `(source_type, Path)` pairs, mirroring `build.iter_md_sources()` /
`build.iter_code_sources()`. To add a new source:

1. Write a function that returns `list[tuple[str, Path]]` for your data.
2. Feed it to `ragcore.build.index_files(conn, model, files, purge_paths=[])`.
3. Add a `classify_type()` branch if you want a new `source_type` label.

Because `index_files` already handles chunking, embedding, and sqlite writes, an
adapter only has to *find* and *label* content.

## Retriever adapters (measure an external retriever)

A *source* adapter feeds the index; a *retriever* adapter goes the other way — it lets the eval
harness (`hitgate/run.py`) measure a retriever from another ecosystem. The harness protocol is any
callable `retrieve(query, top, scope) -> list[{"path": ...}]`, ranked best-first (see
`hitgate/run.py`). An adapter just maps a foreign retriever onto it, and stays **opt-in** — the
core never imports the vendor library.

### LangChain — `adapters/langchain_retriever.py`

`to_harness(lc_retriever, path_key="source")` wraps any LangChain retriever (anything with
`.invoke(query)` / `.get_relevant_documents(query)` returning Documents) into the protocol. The
adapter is dependency-free; it duck-types the interface.

Runnable example over this repo (`adapters/example_langchain_retriever.py`):

```bash
pip install langchain-community           # opt-in; NOT a core dependency
RAG_SOURCE_ROOTS="$PWD" python -m hitgate.run \
    --retriever adapters.example_langchain_retriever:retrieve --label langchain
```

Measured on the demo: `Hit@5 0.917 / Hit@1 0.75 / MRR 0.833`. (That it edges the bundled hybrid
says the 12-case demo is too easy to discriminate retrievers — see `docs/METHODOLOGY.md` — not
that BM25-over-whole-files is better.) To wire your own, mirror the example: build your retriever,
`to_harness(...)` it, expose the callable, and point `--retriever` at it.

### LlamaIndex — `adapters/llamaindex_retriever.py`

`to_harness(li_retriever, path_key="file_path")` wraps any LlamaIndex retriever (anything with
`.retrieve(query)` returning `NodeWithScore` objects) into the protocol. The adapter is
dependency-free; it duck-types the interface and tries both calling conventions for
`similarity_top_k`.

Runnable example over this repo (`adapters/example_llamaindex_retriever.py`):

```bash
pip install llama-index-retrievers-bm25 llama-index-core   # opt-in; NOT core deps
RAG_SOURCE_ROOTS="$PWD" python -m hitgate.run \
    --retriever adapters.example_llamaindex_retriever:retrieve --label llamaindex
```

To wire your own LlamaIndex retriever, build it, `to_harness(...)` it, and point `--retriever`
at it. The `path_key` should match whatever metadata key your loader uses for file paths
(`"file_path"` is the LlamaIndex default; some loaders use `"source"` or `"file_name"`).

## Eval-tracking adapters (push results to experiment trackers)

An *eval-tracking* adapter takes the output of `hitgate/run.py` and pushes it into an
experiment-tracking tool so before/after comparisons are versioned and drillable
instead of hand-diffed JSON. The adapter is strictly opt-in — the core never imports
the vendor library.

### Langfuse — `adapters/langfuse_eval.py`

`push(golden_path, results_path, run_name, dataset_name)` upserts a Langfuse Dataset
from the golden JSONL file and records a named Run with per-item scores
(`hit@1`, `hit@3`, `hit@5`, `mrr_contribution`, `hit_rank`). Items are keyed by
stable position ID so re-runs accumulate as separate experiments against the same
dataset.

```bash
pip install langfuse           # opt-in; NOT a core dependency
export LANGFUSE_PUBLIC_KEY="pk-lf-..."
export LANGFUSE_SECRET_KEY="sk-lf-..."

# Run an eval, then push the results:
python -m hitgate.run --label feat/my-experiment
python adapters/langfuse_eval.py \
    --dataset hitgate/golden.demo.jsonl \
    --results  hitgate/feat-my-experiment.json \
    --run-name "feat/my-experiment"
```

Runnable example: `adapters/example_langfuse_eval.py`. For self-hosted Langfuse,
set `LANGFUSE_HOST=http://your-host:3000`.

## Intentionally out of scope (and why)

This repository was extracted from a personal AI-assistant memory index. Two
integrations from that original system were **left out on purpose**, to keep the
core portable:

- **Agent session-transcript ingestion** — parsing a specific assistant's
  conversation logs into the index. Useful, but it couples the core to one
  vendor's private, undocumented transcript format. It belongs in an adapter, not
  the core.
- **AST code-knowledge-graph integration** — excluding a repo's raw code in favor
  of a separately-built code graph. That depends on an external graph tool; the
  standalone core simply indexes all code uniformly instead (a strict superset of
  the graph-gated behavior).

Both are textbook adapter territory: high value to *one* environment, dead weight
to everyone else. Keeping them out is what makes the core reusable. If you need
one, the contract above is all it takes to add it.
