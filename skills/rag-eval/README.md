# rag-eval skill — portability guide

Copy this skill to `~/.claude/skills/rag-hitgate/` to use it on any repo that implements the harness.

## Installation

```bash
cp -r skills/rag-eval ~/.claude/skills/rag-eval
```

## Env vars

| Var | Default | Purpose |
|-----|---------|---------|
| `RAG_SOURCE_ROOTS` | repo root | Corpus the retriever indexes |
| `RAG_EVAL_DATASET` | `hitgate/golden.demo.jsonl` | Your golden set (`.jsonl`) |
| `RAG_EVAL_BASELINE` | `hitgate/baseline.example.json` | Frozen baseline to compare against |
| `EVAL_EXTRA_FLAGS` | (none) | Extra flags for `run.py` (e.g. `--retriever mypkg:retrieve`) |

All have sensible defaults for this repo out of the box. Override only what differs for your setup.

## Using a custom retriever

```bash
EVAL_EXTRA_FLAGS="--retriever mypkg.myretriever:retrieve"
RAG_EVAL_DATASET="hitgate/my-golden.jsonl"
RAG_EVAL_BASELINE="hitgate/baseline.my-project.json"
bash hitgate/check.sh my-label
```

A retriever is any callable `(query: str, top: int, scope: str | None) -> Sequence[Mapping]` where each result has at least a `"path"` key. See `hitgate/example_external_retriever.py` for a minimal template.

## First-time setup on a new repo

**1. Generate candidate cases from your corpus:**
```bash
RAG_SOURCE_ROOTS="/path/to/your/corpus" python -m hitgate.generate \
    --output hitgate/candidates.jsonl --min-confidence medium
```

**2. Curate** — open `candidates.jsonl`, delete cases where the query is vague or the expected file is wrong.

**3. Run against your retriever:**
```bash
python -m hitgate.run \
    --retriever mypkg.myretriever:retrieve \
    --dataset hitgate/candidates.jsonl \
    --label baseline-v1
```

**4. Freeze the baseline:**
```bash
cp hitgate/baseline-v1.json hitgate/baseline.my-project.json
```

**5. Run the skill** — it will compare every future run against this frozen point.

## LangChain example

```bash
pip install langchain-community
EVAL_EXTRA_FLAGS="--retriever adapters.langchain_retriever:to_harness_retrieve"
RAG_EVAL_BASELINE="hitgate/baseline.langchain.json"
```

See `adapters/langchain_retriever.py` and `adapters/example_langchain_retriever.py` for wiring.
