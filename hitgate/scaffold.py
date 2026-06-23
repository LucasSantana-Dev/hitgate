#!/usr/bin/env python3
"""hitgate onboarding commands: `hitgate-init` and `hitgate-demo`.

Both reduce the from-scratch friction (build -> generate -> curate -> freeze -> gate)
to a single command, EvalView-style. They orchestrate the existing library functions;
they add no new measurement logic.

  hitgate-init [ROOT]   Scaffold a label-free golden set for YOUR corpus (writes
                        eval/golden.jsonl) and print the curate -> freeze -> CI path.
                        Idempotent: refuses to overwrite an existing golden set.

  hitgate-demo [ROOT]   Build a local index, mine a few golden cases, run the gate
                        once, and print the verdict — "see it work on your code".

ROOT defaults to $RAG_SOURCE_ROOTS (first entry) or the current directory.

Both need the bundled engine: `pip install "hitgate[hybrid]"`. Imports are lazy, so
`import hitgate` stays dependency-free and a missing extra produces a clear message.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from hitgate.run import CAVEAT  # CAVEAT shipped in run.py (PR #54); light import, no [hybrid]

_HYBRID_HINT = 'this command needs the bundled engine — `pip install "hitgate[hybrid]"`'


def _resolve_root(arg_root: str | None) -> Path:
    """ROOT precedence: explicit arg > $RAG_SOURCE_ROOTS (first entry) > cwd."""
    if arg_root:
        return Path(arg_root).resolve()
    env = os.environ.get("RAG_SOURCE_ROOTS", "").strip()
    if env:
        return Path(env.split(os.pathsep)[0]).resolve()
    return Path.cwd()


def init(root: Path, output: Path, min_confidence: str = "medium", limit: int = 0) -> int:
    """Scaffold a golden set from `root` into `output`; print the onboarding path.

    Returns a process exit code (0 ok, 1 nothing to scaffold / missing engine).
    """
    # State-check before mutation: never clobber a curated golden set.
    if output.exists():
        print(f"✓ {output} already exists — leaving it untouched (delete it to regenerate).")
        print(f"  Freeze a baseline from it:  python -m hitgate.run --dataset {output} --label baseline")
        return 0

    try:
        from hitgate.generate import _harness_fields, generate
    except ImportError as e:
        print(f"hitgate-init: {_HYBRID_HINT}\n  ({e})", file=sys.stderr)
        return 1

    print(f"Mining a label-free golden set from: {root}")
    candidates = generate(roots=[root], min_confidence=min_confidence, limit=limit)
    if not candidates:
        print(
            f"No candidate cases found under {root}. Point it at a code corpus "
            f"(ROOT arg or $RAG_SOURCE_ROOTS).",
            file=sys.stderr,
        )
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as f:
        for c in candidates:
            f.write(json.dumps(_harness_fields(c)) + "\n")

    print(f"\n✓ Wrote {len(candidates)} candidate case(s) → {output}")
    print(f"\nℹ {CAVEAT}")
    print("\nNext steps:")
    print(f"  1. Curate {output} — drop cases that aren't genuinely answerable from the corpus.")
    print(f'  2. RAG_SOURCE_ROOTS="{root}" python -m ragcore.build      # index your corpus')
    print(f"  3. python -m hitgate.run --dataset {output} --label baseline   # freeze this as your baseline")
    print("  4. Gate it in CI — copy examples/retrieval-gate.yml and set BASELINE_HIT5 from step 3.")
    return 0


def demo(root: Path, limit: int = 12) -> int:
    """Build an index for `root`, mine a few cases, run the gate, print the verdict."""
    try:
        import ragcore.retrieval  # noqa: F401  (presence check for the [hybrid] extra)
    except ImportError as e:
        print(f"hitgate-demo: {_HYBRID_HINT}\n  ({e})", file=sys.stderr)
        return 1

    from hitgate.generate import generate
    from hitgate.run import builtin_retriever
    from hitgate.run import run as run_eval

    print(f"hitgate demo — measuring retrieval on: {root}")
    print("Building a local index (first run downloads a small embedding model)…")
    env = {**os.environ, "RAG_SOURCE_ROOTS": str(root)}
    proc = subprocess.run([sys.executable, "-m", "ragcore.build"], env=env)
    if proc.returncode != 0:
        print("index build failed — see output above.", file=sys.stderr)
        return 1

    cases = generate(roots=[root], min_confidence="medium", limit=limit)
    if not cases:
        print(f"No candidate cases found under {root}.", file=sys.stderr)
        return 1

    result = run_eval(cases, top=5, retriever=builtin_retriever())
    print(
        f"\n[demo]  n={result['n']}  MRR={result['mrr']}  "
        f"hit@1={result['hit@1']}  hit@3={result['hit@3']}  hit@5={result['hit@5']}"
    )
    print(f"ℹ {CAVEAT}")
    print("\nLike it? `hitgate-init` scaffolds a golden set you can curate and gate in CI.")
    return 0


def init_main() -> int:
    ap = argparse.ArgumentParser(
        prog="hitgate-init", description="Scaffold a label-free golden set for your corpus."
    )
    ap.add_argument("root", nargs="?", default=None, help="corpus root (default: $RAG_SOURCE_ROOTS or cwd)")
    ap.add_argument("--output", default="eval/golden.jsonl", help="golden set path (default: eval/golden.jsonl)")
    ap.add_argument("--min-confidence", choices=["high", "medium", "low"], default="medium")
    ap.add_argument("--limit", type=int, default=0, help="cap candidate cases (0 = no limit)")
    args = ap.parse_args()
    return init(_resolve_root(args.root), Path(args.output), args.min_confidence, args.limit)


def demo_main() -> int:
    ap = argparse.ArgumentParser(
        prog="hitgate-demo", description="Run the gate once on a corpus and print the verdict."
    )
    ap.add_argument("root", nargs="?", default=None, help="corpus root (default: $RAG_SOURCE_ROOTS or cwd)")
    ap.add_argument("--limit", type=int, default=12, help="number of golden cases to mine (default: 12)")
    args = ap.parse_args()
    return demo(_resolve_root(args.root), args.limit)


if __name__ == "__main__":
    sys.exit(init_main())
