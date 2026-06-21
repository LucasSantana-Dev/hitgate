"""Runnable example: push a completed eval run to Langfuse.

Prerequisites
-------------
1.  Run an eval:

        RAG_SOURCE_ROOTS="$PWD" python -m ragcore.build
        python -m hitgate.run --label my-run

    This writes ``hitgate/my-run.json``.

2.  Install Langfuse and set credentials:

        pip install langfuse
        export LANGFUSE_PUBLIC_KEY="pk-lf-..."
        export LANGFUSE_SECRET_KEY="sk-lf-..."
        # LANGFUSE_HOST defaults to https://cloud.langfuse.com
        # For self-hosted: export LANGFUSE_HOST="http://localhost:3000"

3.  Run this script from the repo root:

        python adapters/example_langfuse_eval.py

After running, open Langfuse → Datasets → "rag-golden" → Runs to compare
before/after experiments side by side.
"""
import sys
from pathlib import Path

# Allow running from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.langfuse_eval import push

# Paths relative to repo root.
GOLDEN = Path("hitgate/golden.demo.jsonl")
RESULTS = Path("hitgate/my-run.json")

push(
    golden_path=GOLDEN,
    results_path=RESULTS,
    run_name="my-run",
    dataset_name="rag-golden",
)
