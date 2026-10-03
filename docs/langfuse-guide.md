# Catch retrieval regressions in CI and track the scores in Langfuse

Langfuse stores whatever scores you give it. It has no built-in ranking metric for a
retriever. hitgate fills that gap without labels: it scores a retriever on Hit@K and MRR,
and a small adapter pushes those scores into a Langfuse Dataset run, so each change to
chunking, embeddings or a reranker shows up as its own comparable experiment.

**Know the limit first.** hitgate's auto-generated queries come from the indexed text, so
absolute scores run optimistic (FastAPI check: Hit@5 1.00 auto-mined vs 0.92 hand-labeled,
see [two-channel-fastapi.md](./two-channel-fastapi.md)). Use it to detect regressions
between two runs, not to certify absolute quality.

## 1. Install

```bash
pip install hitgate langfuse
```

`langfuse` is opt-in. hitgate's core never imports it.

## 2. Point hitgate at your retriever and run it

A retriever is any callable `(query, top, scope) -> [{"path": ...}]`. See the
[README](../README.md) for the contract and `hitgate/example_external_retriever.py` for a
dependency-free example.

```bash
python -m hitgate.run --retriever mypkg.myretriever:retrieve --label baseline
# change something (chunking, embeddings, reranker), then:
python -m hitgate.run --retriever mypkg.myretriever:retrieve --label candidate
python -m hitgate.diff baseline.json candidate.json
```

Each run writes `<label>.json` in the current directory and prints the path.
`hitgate.diff` shows which cases moved. Add `--dataset your-golden.jsonl` to use your own
queries instead of the bundled demo set. `python -m hitgate.generate --output
candidates.jsonl` bootstraps a candidate set from your corpus.

## 3. Push each run to Langfuse

```bash
export LANGFUSE_PUBLIC_KEY=...    # from your Langfuse project settings
export LANGFUSE_SECRET_KEY=...
# self-hosted: export LANGFUSE_HOST=http://your-host:3000

python -m hitgate.adapters.langfuse_eval \
    --dataset your-golden.jsonl \
    --results candidate.json \
    --run-name "candidate"
```

`--dataset` must be the same golden file you used for the run.

What it creates (from `hitgate/adapters/langfuse_eval.py`):

- A Dataset (default name `rag-golden`, change with `--dataset-name`), one item per golden
  case, keyed by stable position so re-pushes are idempotent.
- A run named by `--run-name`, with per-item scores `hit@1`, `hit@3`, `hit@5`,
  `mrr_contribution` and `hit_rank`.

Push `baseline` the same way. In Langfuse, open Datasets, pick the dataset, then Runs to
compare the two side by side.

## 4. Gate it in CI

Keep Langfuse as the record and let hitgate be the gate:

```bash
python -m hitgate.compare candidate.json baseline.json 5
```

It exits 1 if any metric regresses by more than 5 percentage points (the last argument is
the tolerance), 0 otherwise. Run it before the Langfuse push step, with `if: always()` on
the push, so passing and failing runs are both recorded.

## Python API

```python
from hitgate.adapters.langfuse_eval import push

push("your-golden.jsonl", "candidate.json", run_name="candidate", dataset_name="rag-golden")
```

## Related

- [Adapters overview](../hitgate/adapters/README.md)
- [Methodology and limits](./METHODOLOGY.md)
