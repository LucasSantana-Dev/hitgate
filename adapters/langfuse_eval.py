"""Opt-in adapter: push evidence-first-rag eval results into Langfuse Datasets/Experiments.

This file has **no hard dependency** on Langfuse — it imports the SDK lazily so the
core never requires it. Install the optional dep only when you want tracking:

    pip install langfuse           # opt-in; NOT a core dependency

Usage (CLI):

    # After an eval run, push the dataset + results to Langfuse:
    python adapters/langfuse_eval.py \\
        --dataset eval/golden.demo.jsonl \\
        --results  eval/my-run.json \\
        --run-name "feat/chunk-prefixing"

    # Langfuse reads credentials from env (or .env):
    #   LANGFUSE_PUBLIC_KEY  pk-lf-...
    #   LANGFUSE_SECRET_KEY  sk-lf-...
    #   LANGFUSE_HOST        https://cloud.langfuse.com  (default)

What gets created / updated in Langfuse:
  - A Dataset named after --dataset-name (default: "rag-golden").
  - One DatasetItem per golden case (idempotent; keyed by stable item ID).
  - A run named after --run-name with aggregate and per-item scores.

Scores recorded per item:
  hit@1, hit@3, hit@5  (1.0 or 0.0)
  mrr_contribution     (1/rank if found, else 0.0)
  hit_rank             (integer rank of expected path, or 0 for miss)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def push(
    golden_path: str | Path,
    results_path: str | Path,
    run_name: str,
    dataset_name: str = "rag-golden",
    langfuse_client: Any = None,
) -> None:
    """Push eval results to Langfuse.

    Parameters
    ----------
    golden_path:
        Path to the golden JSONL file used for the eval run.
    results_path:
        Path to the JSON output of ``eval/run.py``.
    run_name:
        Experiment / run name shown in the Langfuse UI.
    dataset_name:
        Name of the Langfuse Dataset to create or update.
    langfuse_client:
        Pre-built Langfuse client (for testing).  If None, one is constructed
        from ``LANGFUSE_PUBLIC_KEY`` / ``LANGFUSE_SECRET_KEY`` / ``LANGFUSE_HOST``
        environment variables.
    """
    try:
        from langfuse import Langfuse  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "langfuse is not installed — run: pip install langfuse"
        ) from exc

    lf: Any = langfuse_client or Langfuse()

    # Load the golden cases.
    golden_path = Path(golden_path)
    cases = [json.loads(line) for line in golden_path.read_text().splitlines() if line.strip()]

    # Load the per-case eval results.
    results = json.loads(Path(results_path).read_text())
    per_case: list[dict] = results.get("per_case", [])
    by_query: dict[str, dict] = {r["query"]: r for r in per_case}

    # --- Upsert dataset items ---
    lf.create_dataset(name=dataset_name, description=f"Loaded from {golden_path.name}")
    for i, case in enumerate(cases):
        lf.create_dataset_item(
            dataset_name=dataset_name,
            input={"query": case["query"]},
            expected_output={
                "path_contains": case.get("expect_path_contains", ""),
                "scope": case.get("expect_scope", ""),
                "intent": case.get("intent", ""),
                "paraphrase": case.get("paraphrase", False),
            },
            id=f"{golden_path.stem}:{i}",  # stable per-position ID
        )

    # --- Record the run, one trace per item ---
    dataset = lf.get_dataset(dataset_name)
    for item in dataset.items:
        # Match back to the result by query (items may be in different order).
        query = item.input.get("query", "")
        result = by_query.get(query)
        if result is None:
            continue

        hit_rank: int | None = result.get("hit_rank")  # None = miss
        rank_int = hit_rank if hit_rank else 0

        with item.observe(run_name=run_name) as trace:
            trace.update(
                output={
                    "top_hit": result.get("top_hit", ""),
                    "hit_rank": hit_rank,
                },
                metadata={
                    "scope": result.get("scope", ""),
                    "intent": result.get("intent", ""),
                },
            )
            trace.score(name="hit@1", value=float(rank_int == 1))
            trace.score(name="hit@3", value=float(0 < rank_int <= 3))
            trace.score(name="hit@5", value=float(0 < rank_int <= 5))
            trace.score(name="mrr_contribution", value=1.0 / rank_int if rank_int else 0.0)
            trace.score(name="hit_rank", value=float(rank_int))

    lf.flush()
    n = len(cases)
    print(f"Pushed {n} items to dataset '{dataset_name}', run '{run_name}'.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Push evidence-first-rag eval results to Langfuse Datasets/Experiments."
    )
    ap.add_argument("--dataset", required=True, help="path to golden .jsonl file")
    ap.add_argument("--results", required=True, help="path to eval run .json output")
    ap.add_argument("--run-name", required=True, help="experiment / run name in Langfuse")
    ap.add_argument(
        "--dataset-name",
        default="rag-golden",
        help="Langfuse dataset name (default: rag-golden)",
    )
    args = ap.parse_args()
    push(
        golden_path=args.dataset,
        results_path=args.results,
        run_name=args.run_name,
        dataset_name=args.dataset_name,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
