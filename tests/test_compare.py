"""Tests for eval/compare.py — the retrieval comparison and verdict module.

Tests verify external behavior: given two result JSON dicts and a tolerance,
assert the correct verdict, regression list, deltas, and refreeze flag.
Filesystem writes (verdict.json) and text output are not tested here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from hitgate.compare import compare


def _result(hit5=1.0, hit3=0.9, hit1=0.6, mrr=0.75, by_intent=None, by_scope=None) -> dict:
    out = {"mrr": mrr, "hit@1": hit1, "hit@3": hit3, "hit@5": hit5}
    if by_intent is not None:
        out["by_intent"] = by_intent
    if by_scope is not None:
        out["by_scope"] = by_scope
    return out


def _intent(hit5=1.0, n=15) -> dict:
    return {"n": n, "hit@5": hit5, "hit@1": 0.6, "hit@3": 0.9, "mrr": 0.75}


def _scope(hit5=1.0, n=30) -> dict:
    return {"n": n, "hit@5": hit5, "hit@1": 0.6, "hit@3": 0.9, "mrr": 0.75}


# ---------------------------------------------------------------------------
# Pass cases
# ---------------------------------------------------------------------------

def test_identical_runs_pass():
    base = _result()
    v = compare(base, base)
    assert v["verdict"] == "pass"
    assert v["regressions"] == []
    assert v["refreeze_recommended"] is False


def test_small_drop_within_tolerance_passes():
    # 4pp drop on hit@5 — below the 5pp threshold
    cur = _result(hit5=0.96)
    base = _result(hit5=1.0)
    v = compare(cur, base)
    assert v["verdict"] == "pass"
    assert v["regressions"] == []


# ---------------------------------------------------------------------------
# Regression cases
# ---------------------------------------------------------------------------

def test_aggregate_regression_detected():
    cur = _result(hit5=0.90)
    base = _result(hit5=1.0)
    v = compare(cur, base)
    assert v["verdict"] == "regression"
    assert any(r["metric"] == "hit@5" and r["scope"] == "aggregate" for r in v["regressions"])
    assert v["deltas"]["hit@5"] == pytest.approx(-0.10, abs=1e-4)


def test_per_intent_regression_detected():
    # Aggregate holds but one intent class drops
    cur = _result(
        hit5=1.0,
        by_intent={"indexing": _intent(hit5=0.80), "retrieval": _intent(hit5=1.0)},
    )
    base = _result(
        hit5=1.0,
        by_intent={"indexing": _intent(hit5=1.0), "retrieval": _intent(hit5=1.0)},
    )
    v = compare(cur, base)
    assert v["verdict"] == "regression"
    assert any(r["scope"] == "intent:indexing" for r in v["regressions"])
    assert not any(r["scope"] == "intent:retrieval" for r in v["regressions"])


def test_boundary_exactly_at_tolerance_is_pass():
    # Delta of exactly -5pp is NOT a regression (threshold is strict <)
    cur = _result(hit5=0.95)
    base = _result(hit5=1.0)
    v = compare(cur, base)
    assert v["verdict"] == "pass"
    assert v["regressions"] == []


# ---------------------------------------------------------------------------
# Improvement / refreeze
# ---------------------------------------------------------------------------

def test_hit5_improvement_beyond_tolerance_sets_refreeze():
    cur = _result(hit5=1.0)
    base = _result(hit5=0.90)
    v = compare(cur, base)
    assert v["verdict"] == "improvement"
    assert v["refreeze_recommended"] is True
    assert v["regressions"] == []


# ---------------------------------------------------------------------------
# Missing by_intent — graceful fallback
# ---------------------------------------------------------------------------

def test_missing_by_intent_in_baseline_is_graceful():
    cur = _result(hit5=0.90, by_intent={"indexing": _intent()})
    base = _result(hit5=1.0)  # no by_intent
    # Should detect aggregate regression; per-intent gate silently skipped
    v = compare(cur, base)
    assert v["verdict"] == "regression"
    assert all(r["scope"] == "aggregate" for r in v["regressions"])


def test_missing_by_intent_in_current_is_graceful():
    cur = _result(hit5=1.0)  # no by_intent
    base = _result(hit5=1.0, by_intent={"indexing": _intent()})
    v = compare(cur, base)
    assert v["verdict"] == "pass"
    assert v["regressions"] == []


# ---------------------------------------------------------------------------
# by_scope gating — catches regressions masked at aggregate level
# ---------------------------------------------------------------------------


def test_per_scope_regression_detected():
    # Aggregate holds at 1.0, but code scope drops to 0.8 — should catch regression
    cur = _result(
        hit5=1.0,
        by_scope={"code": _scope(hit5=0.80), "markdown": _scope(hit5=1.0)},
    )
    base = _result(
        hit5=1.0,
        by_scope={"code": _scope(hit5=1.0), "markdown": _scope(hit5=1.0)},
    )
    v = compare(cur, base)
    assert v["verdict"] == "regression"
    assert any(r["scope"] == "scope:code" for r in v["regressions"])
    assert not any(r["scope"] == "scope:markdown" for r in v["regressions"])


def test_scope_regression_masked_at_aggregate_is_caught():
    # Demonstrate the gap this gate fills: a regression in code scope masked by
    # improvements in markdown, but aggregate hit@5 stays at 1.0
    cur = _result(
        hit5=1.0,  # aggregate unchanged
        by_scope={
            "code": _scope(hit5=0.90, n=50),       # -10pp in code
            "markdown": _scope(hit5=1.0, n=51),    # unchanged in markdown
        },
    )
    base = _result(
        hit5=1.0,
        by_scope={
            "code": _scope(hit5=1.0, n=50),
            "markdown": _scope(hit5=1.0, n=51),
        },
    )
    v = compare(cur, base)
    # Aggregate gate passes (0 delta) but per-scope gate catches the -10pp code regression
    assert v["verdict"] == "regression"
    assert any(r["scope"] == "scope:code" and r["metric"] == "hit@5" for r in v["regressions"])
    assert v["deltas"]["hit@5"] == 0.0  # aggregate unchanged


def test_missing_by_scope_in_baseline_is_graceful():
    cur = _result(hit5=1.0, by_scope={"code": _scope()})
    base = _result(hit5=1.0)  # no by_scope
    # Should detect nothing (both conditions empty); no crash
    v = compare(cur, base)
    assert v["verdict"] == "pass"
    assert v["regressions"] == []


def test_missing_by_scope_in_current_is_graceful():
    cur = _result(hit5=1.0)  # no by_scope
    base = _result(hit5=1.0, by_scope={"code": _scope()})
    v = compare(cur, base)
    assert v["verdict"] == "pass"
    assert v["regressions"] == []


# ---------------------------------------------------------------------------
# print_table — human-readable output regression test
# ---------------------------------------------------------------------------


def test_print_table_aggregate_only(capsys):
    """print_table renders aggregate metrics and flags regressions."""
    from hitgate.compare import print_table

    cur = _result(hit5=0.90)  # regression
    base = _result(hit5=1.0)
    v = compare(cur, base)

    print_table(cur, base, v, tol_pp=5.0)
    captured = capsys.readouterr().out

    # Should show delta with ⚠ marker
    assert "⚠ REGRESSION" in captured
    assert "hit@5" in captured
    assert "0.900" in captured
    assert "Delta vs baseline" in captured


def test_print_table_per_scope_regression(capsys):
    """print_table shows per-scope section with regression marker."""
    from hitgate.compare import print_table

    cur = _result(
        hit5=1.0,
        by_scope={"code": _scope(hit5=0.80), "markdown": _scope(hit5=1.0)},
    )
    base = _result(
        hit5=1.0,
        by_scope={"code": _scope(hit5=1.0), "markdown": _scope(hit5=1.0)},
    )
    v = compare(cur, base)
    print_table(cur, base, v, tol_pp=5.0)
    captured = capsys.readouterr().out

    assert "Per-scope Hit@5" in captured
    assert "code" in captured
    assert "⚠ REGRESSION" in captured
    # markdown scope should be shown but without regression marker
    assert "markdown" in captured


def test_print_table_per_intent_no_regressions(capsys):
    """print_table shows per-intent section only when both have it."""
    from hitgate.compare import print_table

    cur = _result(
        hit5=1.0,
        by_intent={"indexing": _intent(hit5=1.0), "retrieval": _intent(hit5=1.0)},
    )
    base = _result(
        hit5=1.0,
        by_intent={"indexing": _intent(hit5=1.0), "retrieval": _intent(hit5=1.0)},
    )
    v = compare(cur, base)
    print_table(cur, base, v, tol_pp=5.0)
    captured = capsys.readouterr().out

    assert "Per-intent Hit@5" in captured
    assert "✓ within tolerance" in captured
    assert "⚠ REGRESSION" not in captured


def test_print_table_improvement_refreeze_message(capsys):
    """print_table shows refreeze recommendation for improvements."""
    from hitgate.compare import print_table

    cur = _result(hit5=1.0)
    base = _result(hit5=0.90)
    v = compare(cur, base)
    print_table(cur, base, v, tol_pp=5.0)
    captured = capsys.readouterr().out

    assert "Hit@5 improved" in captured
    assert "re-freezing the baseline" in captured


def test_print_table_no_by_scope_hides_section(capsys):
    """print_table only shows per-scope section if both results have it."""
    from hitgate.compare import print_table

    cur = _result(hit5=1.0)  # no by_scope
    base = _result(hit5=1.0)  # no by_scope
    v = compare(cur, base)
    print_table(cur, base, v, tol_pp=5.0)
    captured = capsys.readouterr().out

    assert "Per-scope Hit@5" not in captured
    assert "Per-intent Hit@5" not in captured
    assert "✓ within tolerance" in captured


# ---------------------------------------------------------------------------
# main() — CLI entry point, file I/O and exit codes
# ---------------------------------------------------------------------------


def test_main_writes_verdict_json(tmp_path):
    """main() writes <current>.verdict.json and returns 0 on pass."""
    from hitgate.compare import main

    cur = _result(hit5=1.0)
    base = _result(hit5=1.0)

    cur_path = tmp_path / "cur.json"
    base_path = tmp_path / "base.json"
    cur_path.write_text(json.dumps(cur))
    base_path.write_text(json.dumps(base))

    # Mock sys.argv
    old_argv = sys.argv
    try:
        sys.argv = ["compare.py", str(cur_path), str(base_path)]
        code = main()
    finally:
        sys.argv = old_argv

    assert code == 0  # pass
    verdict_path = tmp_path / "cur.verdict.json"
    assert verdict_path.exists()
    verdict = json.loads(verdict_path.read_text())
    assert verdict["verdict"] == "pass"


def test_main_returns_1_on_regression(tmp_path, capsys):
    """main() returns 1 when a regression is detected."""
    from hitgate.compare import main

    cur = _result(hit5=0.90)  # regression
    base = _result(hit5=1.0)

    cur_path = tmp_path / "cur.json"
    base_path = tmp_path / "base.json"
    cur_path.write_text(json.dumps(cur))
    base_path.write_text(json.dumps(base))

    old_argv = sys.argv
    try:
        sys.argv = ["compare.py", str(cur_path), str(base_path)]
        code = main()
    finally:
        sys.argv = old_argv

    assert code == 1  # regression
    verdict_path = tmp_path / "cur.verdict.json"
    verdict = json.loads(verdict_path.read_text())
    assert verdict["verdict"] == "regression"


def test_main_returns_0_on_improvement(tmp_path):
    """main() returns 0 when improvement is detected (refreeze recommended)."""
    from hitgate.compare import main

    cur = _result(hit5=1.0)
    base = _result(hit5=0.90)

    cur_path = tmp_path / "cur.json"
    base_path = tmp_path / "base.json"
    cur_path.write_text(json.dumps(cur))
    base_path.write_text(json.dumps(base))

    old_argv = sys.argv
    try:
        sys.argv = ["compare.py", str(cur_path), str(base_path)]
        code = main()
    finally:
        sys.argv = old_argv

    assert code == 0  # improvement (still pass)
    verdict_path = tmp_path / "cur.verdict.json"
    verdict = json.loads(verdict_path.read_text())
    assert verdict["verdict"] == "improvement"
    assert verdict["refreeze_recommended"] is True


def test_main_parses_custom_tolerance(tmp_path):
    """main() parses custom tol_pp from argv[3]."""
    from hitgate.compare import main

    cur = _result(hit5=0.95)  # 5pp drop
    base = _result(hit5=1.0)

    cur_path = tmp_path / "cur.json"
    base_path = tmp_path / "base.json"
    cur_path.write_text(json.dumps(cur))
    base_path.write_text(json.dumps(base))

    old_argv = sys.argv
    try:
        # tol_pp=3 means 5pp drop is a regression
        sys.argv = ["compare.py", str(cur_path), str(base_path), "3"]
        code = main()
    finally:
        sys.argv = old_argv

    assert code == 1  # regression with tol_pp=3
    verdict_path = tmp_path / "cur.verdict.json"
    verdict = json.loads(verdict_path.read_text())
    assert verdict["tolerance_pp"] == 3.0
    assert verdict["verdict"] == "regression"


def test_main_missing_args_exits(capsys):
    """main() exits with usage error if <3 args."""
    from hitgate.compare import main

    old_argv = sys.argv
    try:
        sys.argv = ["compare.py"]
        with pytest.raises(SystemExit):
            main()
    finally:
        sys.argv = old_argv
