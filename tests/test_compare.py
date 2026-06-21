"""Tests for eval/compare.py — the retrieval comparison and verdict module.

Tests verify external behavior: given two result JSON dicts and a tolerance,
assert the correct verdict, regression list, deltas, and refreeze flag.
Filesystem writes (verdict.json) and text output are not tested here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from hitgate.compare import compare


def _result(hit5=1.0, hit3=0.9, hit1=0.6, mrr=0.75, by_intent=None) -> dict:
    out = {"mrr": mrr, "hit@1": hit1, "hit@3": hit3, "hit@5": hit5}
    if by_intent is not None:
        out["by_intent"] = by_intent
    return out


def _intent(hit5=1.0, n=15) -> dict:
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
