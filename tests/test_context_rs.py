"""Cross-check: the Rust binary (rust/hitgate-context) and hitgate.context agree.

Skipped when the binary has not been built. Set HITGATE_CONTEXT_RS to point at a binary
elsewhere.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_context import _corpus

REPO = Path(__file__).resolve().parents[1]
CRATE = REPO / "rust" / "hitgate-context"
EXE = ".exe" if os.name == "nt" else ""


def _binary() -> Path | None:
    env = os.environ.get("HITGATE_CONTEXT_RS")
    if env:
        return Path(env)
    for profile in ("release", "debug"):
        p = CRATE / "target" / profile / f"hitgate-context{EXE}"
        if p.is_file():
            return p
    return None


BIN = _binary()
pytestmark = pytest.mark.skipif(BIN is None, reason="rust binary not built (cargo build --release)")


def _rust(root: Path, out: Path, label: str, baseline: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [str(BIN), str(root), "--out", str(out), "--label", label]
    if baseline:
        cmd += ["--baseline", str(baseline)]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _python(root: Path, out: Path, label: str, baseline: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "hitgate.context", str(root), "--out", str(out), "--label", label]
    if baseline:
        cmd += ["--baseline", str(baseline)]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")  # the table prints arrows; cp1252 consoles reject them
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=REPO, env=env)


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _ranks(result: dict) -> list[tuple[str, str, int | None]]:
    return [(c["query"], c["expect"], c["hit_rank"]) for c in result["per_case"]]


def _break(root: Path) -> None:
    (root / "skills" / "ship" / "SKILL.md").write_text(
        "---\nname: ship\ndescription: Do the thing.\ntriggers:\n  - ship\n  - \"cut a release\"\n---\n",
        encoding="utf-8",
    )
    (root / "skills" / "verify" / "SKILL.md").write_text(
        "---\nname: verify\ndescription: Cut a release and ship validated work to production with a release tag.\n"
        "auto-invoke: run checks, validate this\n---\n",
        encoding="utf-8",
    )


def test_same_results_over_fixture_corpus(tmp_path: Path) -> None:
    root = tmp_path / "ctx"
    _corpus(root)
    py = _python(root, tmp_path / "py", "x")
    rs = _rust(root, tmp_path / "rs", "x")
    assert py.returncode == 0, py.stderr
    assert rs.returncode == 0, rs.stderr
    a = _load(tmp_path / "py" / "context.x.json")
    b = _load(tmp_path / "rs" / "context.x.json")
    assert _ranks(a) == _ranks(b)
    for key in ("n", "mrr", "hit@1", "hit@3", "hit@5", "by_scope", "by_intent", "docs", "shadowed"):
        assert a[key] == b[key], key
    assert a == b


def test_same_results_on_a_broken_corpus(tmp_path: Path) -> None:
    root = tmp_path / "ctx"
    _corpus(root)
    _break(root)
    py = _python(root, tmp_path / "py", "x")
    rs = _rust(root, tmp_path / "rs", "x")
    assert py.returncode == 0 and rs.returncode == 0
    a = _load(tmp_path / "py" / "context.x.json")
    b = _load(tmp_path / "rs" / "context.x.json")
    assert a == b
    assert any(c["hit_rank"] != 1 for c in a["per_case"])


def test_python_baseline_gates_rust_run(tmp_path: Path) -> None:
    root = tmp_path / "ctx"
    _corpus(root)
    assert _python(root, tmp_path / "base", "base").returncode == 0
    baseline = tmp_path / "base" / "context.base.json"
    same = _rust(root, tmp_path / "same", "same", baseline)
    assert same.returncode == 0, same.stdout + same.stderr
    assert _load(tmp_path / "same" / "context.same.verdict.json")["verdict"] == "pass"
    _break(root)
    broken = _rust(root, tmp_path / "broken", "broken", baseline)
    assert broken.returncode == 1, broken.stdout + broken.stderr
    assert _load(tmp_path / "broken" / "context.broken.verdict.json")["verdict"] == "regression"


def test_rust_baseline_gates_python_run(tmp_path: Path) -> None:
    root = tmp_path / "ctx"
    _corpus(root)
    assert _rust(root, tmp_path / "base", "base").returncode == 0
    baseline = tmp_path / "base" / "context.base.json"
    same = _python(root, tmp_path / "same", "same", baseline)
    assert same.returncode == 0, same.stdout + same.stderr
    _break(root)
    broken = _python(root, tmp_path / "broken", "broken", baseline)
    assert broken.returncode == 1, broken.stdout + broken.stderr
    py_verdict = _load(tmp_path / "broken" / "context.broken.verdict.json")
    rs_broken = _rust(root, tmp_path / "rs-broken", "broken", baseline)
    assert rs_broken.returncode == 1
    rs_verdict = _load(tmp_path / "rs-broken" / "context.broken.verdict.json")
    assert py_verdict == rs_verdict
