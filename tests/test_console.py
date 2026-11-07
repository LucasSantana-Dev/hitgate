"""CLIs must not crash on a console whose encoding cannot print arrows and check marks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from test_context import _corpus

REPO = Path(__file__).resolve().parents[1]


def _run(args: list[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="cp1252")  # a legacy Windows console code page
    return subprocess.run(
        [sys.executable, *args], capture_output=True, cwd=REPO, env=env, timeout=120
    )


def test_context_gate_report_survives_cp1252(tmp_path: Path) -> None:
    root = tmp_path / "ctx"
    _corpus(root)
    assert _run(["-m", "hitgate.context", str(root), "--out", str(tmp_path), "--label", "base"]).returncode == 0
    baseline = tmp_path / "context.base.json"
    p = _run(["-m", "hitgate.context", str(root), "--out", str(tmp_path), "--label", "cur", "--baseline", str(baseline)])
    assert b"UnicodeEncodeError" not in p.stderr, p.stderr.decode("cp1252", "replace")
    assert p.returncode == 0
    assert json.loads((tmp_path / "context.cur.verdict.json").read_text(encoding="utf-8"))["verdict"] == "pass"


def test_compare_table_survives_cp1252(tmp_path: Path) -> None:
    cur = {"n": 2, "mrr": 1.0, "hit@1": 1.0, "hit@3": 1.0, "hit@5": 1.0, "by_scope": {}, "by_intent": {}}
    base = dict(cur, mrr=0.5, **{"hit@1": 0.5})
    (tmp_path / "cur.json").write_text(json.dumps(cur), encoding="utf-8")
    (tmp_path / "base.json").write_text(json.dumps(base), encoding="utf-8")
    p = _run(["-m", "hitgate.compare", str(tmp_path / "cur.json"), str(tmp_path / "base.json")])
    assert b"UnicodeEncodeError" not in p.stderr, p.stderr.decode("cp1252", "replace")
    assert p.returncode == 0
