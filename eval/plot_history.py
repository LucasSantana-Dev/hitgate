#!/usr/bin/env python3
"""eval/plot_history.py — Hit@5 across git history (per-commit, self-indexed).

Walks recent commits on the current branch and, for each one that ships the eval
harness, checks it out into a throwaway `git worktree`, indexes that commit's own
source (the demo self-indexes the repo), runs the pure-hybrid eval (rerank off),
and records Hit@5. Writes `docs/hit5_history.svg` and a `docs/hit5_history.json`
data file so the chart is reproducible and auditable.

HONEST CAVEATS (by design, not hidden — see the chart caption too):
- Each point is that commit's eval of ITSELF. The demo self-indexes the repo, so the
  corpus grows with the project; movement mixes retriever changes with corpus growth.
- The harness + golden set are each commit's own (per-commit-native), so the measuring
  stick evolves across history. This is the project's real measured trajectory, not a
  controlled A/B. For a single-ruler ablation, see docs/METHODOLOGY.md.

Charting needs matplotlib (optional dev dependency): `pip install -r requirements-dev.txt`.
The eval run itself needs only the three core deps.

Usage:
  python eval/plot_history.py [--max-commits N] [--branch main]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
EVAL_REL = "eval/run.py"
GOLDEN_REL = "eval/golden.demo.jsonl"


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(cwd or ROOT), check=True, capture_output=True, text=True
    ).stdout.strip()


def commits(branch: str, limit: int) -> list[tuple[str, str, str]]:
    """(sha, iso-date, subject) oldest→newest for the last `limit` commits on `branch`."""
    out = git("log", f"-n{limit}", "--first-parent", "--format=%H%x09%cs%x09%s", branch)
    rows = [tuple(line.split("\t", 2)) for line in out.splitlines() if line.strip()]
    return list(reversed(rows))  # oldest first for a left→right timeline


def hit5_at(sha: str) -> float | None:
    """Eval Hit@5 for one commit in an isolated worktree; None if it can't be measured."""
    with tempfile.TemporaryDirectory(prefix="efr-hist-") as tmp:
        wt = Path(tmp) / "wt"
        try:
            git("worktree", "add", "--detach", "--quiet", str(wt), sha)
        except subprocess.CalledProcessError:
            return None
        try:
            if not (wt / EVAL_REL).exists() or not (wt / GOLDEN_REL).exists():
                return None  # harness didn't exist yet at this commit — skip honestly
            env = {
                "RAG_SOURCE_ROOTS": str(wt),
                "RAG_RERANK_AUTO": "off",
                "RAG_INDEX_DIR": str(wt / ".rag-index"),
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "PATH": __import__("os").environ.get("PATH", ""),
                "HOME": __import__("os").environ.get("HOME", ""),
            }
            build = wt / "ragcore" / "build.py"
            if not build.exists():
                return None
            r = subprocess.run([sys.executable, str(build)], cwd=str(wt), env=env, capture_output=True, text=True)
            if r.returncode != 0:
                return None
            r = subprocess.run(
                [sys.executable, EVAL_REL, "--label", "hist"], cwd=str(wt), env=env,
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                return None
            out = wt / "eval" / "hist.json"
            if not out.exists():
                return None
            h5 = json.loads(out.read_text()).get("hit@5")
            return float(h5) if h5 is not None else None  # skip (don't crash) on a malformed run
        finally:
            git("worktree", "remove", "--force", str(wt))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-commits", type=int, default=20)
    ap.add_argument("--branch", default="main")
    args = ap.parse_args()

    DOCS.mkdir(exist_ok=True)
    points = []
    for sha, date, subject in commits(args.branch, args.max_commits):
        h5 = hit5_at(sha)
        status = f"Hit@5={h5}" if h5 is not None else "skipped (no harness/failed)"
        print(f"  {sha[:8]} {date}  {status}  — {subject[:50]}")
        if h5 is not None:
            points.append({"sha": sha[:8], "date": date, "subject": subject, "hit5": h5})

    if not points:
        sys.exit("no measurable commits — nothing to plot")

    (DOCS / "hit5_history.json").write_text(json.dumps(points, indent=2))
    print(f"\nwrote {DOCS / 'hit5_history.json'} ({len(points)} measured commits)")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        sys.exit(
            "matplotlib not installed — wrote the data file but not the chart.\n"
            "Install the optional dev dep: pip install -r requirements-dev.txt"
        )

    xs = list(range(len(points)))
    ys = [p["hit5"] for p in points]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.plot(xs, ys, marker="o", color="#2563eb", linewidth=2)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Hit@5 (code scope, pure hybrid)")
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{p['sha']}\n{p['date']}" for p in points], rotation=45, ha="right", fontsize=7)
    ax.set_title("evidence-first-rag — Hit@5 per commit (self-indexed, per-commit-native eval)")
    ax.grid(True, axis="y", alpha=0.3)
    ax.text(
        0.0, -0.42,
        "Each point = that commit's eval of itself (the demo self-indexes the repo, so the corpus grows with it; "
        "the harness is each commit's own). Real trajectory, not a controlled A/B — see METHODOLOGY.md for the single-ruler ablation.",
        transform=ax.transAxes, fontsize=6.5, color="#555", wrap=True,
    )
    fig.tight_layout()
    out = DOCS / "hit5_history.svg"
    fig.savefig(out, format="svg", bbox_inches="tight")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
