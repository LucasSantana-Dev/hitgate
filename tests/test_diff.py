"""Tests for hitgate/diff.py — per-case rank change classification.

Tests verify: REGRESSION (rank worsens), IMPROVEMENT (rank improves),
MIXED (both), IDENTICAL (no changes). Handles None (MISS) correctly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


def _result(per_case: list[dict]) -> dict:
    """Build a minimal eval result with per_case data."""
    return {
        "n": len(per_case),
        "hit@1": 0.0,
        "hit@3": 0.0,
        "hit@5": 0.0,
        "mrr": 0.0,
        "per_case": per_case,
    }


# ---------------------------------------------------------------------------
# rank_label — format for display
# ---------------------------------------------------------------------------


def test_rank_label_formats_numeric():
    """rank_label formats numeric ranks as #1, #2, etc."""
    from hitgate.diff import rank_label

    assert rank_label(1) == "#1"
    assert rank_label(5) == "#5"
    assert rank_label(99) == "#99"


def test_rank_label_formats_miss():
    """rank_label formats None as MISS."""
    from hitgate.diff import rank_label

    assert rank_label(None) == "MISS"


# ---------------------------------------------------------------------------
# Verdict classification — REGRESSION/IMPROVEMENT/MIXED/IDENTICAL
# ---------------------------------------------------------------------------


def test_diff_regression_when_rank_worsens(tmp_path, capsys):
    """diff classifies verdict as REGRESSION when rank worsens."""
    from hitgate.diff import main

    base = _result([
        {"query": "q1", "hit_rank": 1, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": "target.py:10"},
    ])
    head = _result([
        {"query": "q1", "hit_rank": 5, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": "other.py:1"},
    ])

    base_path = tmp_path / "base.json"
    head_path = tmp_path / "head.json"
    base_path.write_text(json.dumps(base))
    head_path.write_text(json.dumps(head))

    old_argv = sys.argv
    try:
        sys.argv = ["diff.py", str(base_path), str(head_path)]
        code = main()
    finally:
        sys.argv = old_argv

    captured = capsys.readouterr().out
    assert "REGRESSION" in captured
    assert code == 1


def test_diff_improvement_when_rank_improves(tmp_path, capsys):
    """diff classifies verdict as IMPROVEMENT when rank improves."""
    from hitgate.diff import main

    base = _result([
        {"query": "q1", "hit_rank": 5, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": "other.py:1"},
    ])
    head = _result([
        {"query": "q1", "hit_rank": 1, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": "target.py:10"},
    ])

    base_path = tmp_path / "base.json"
    head_path = tmp_path / "head.json"
    base_path.write_text(json.dumps(base))
    head_path.write_text(json.dumps(head))

    old_argv = sys.argv
    try:
        sys.argv = ["diff.py", str(base_path), str(head_path)]
        code = main()
    finally:
        sys.argv = old_argv

    captured = capsys.readouterr().out
    assert "IMPROVED" in captured
    assert code == 0


def test_diff_mixed_when_both_improve_and_regress(tmp_path, capsys):
    """diff classifies verdict as MIXED when some improve and some regress."""
    from hitgate.diff import main

    base = _result([
        {"query": "q1", "hit_rank": 1, "expect": "target1.py", "scope": "code", "intent": "retrieval", "top_hit": "target1.py:10"},
        {"query": "q2", "hit_rank": 5, "expect": "target2.py", "scope": "code", "intent": "retrieval", "top_hit": "other.py:1"},
    ])
    head = _result([
        {"query": "q1", "hit_rank": 5, "expect": "target1.py", "scope": "code", "intent": "retrieval", "top_hit": "other.py:1"},
        {"query": "q2", "hit_rank": 1, "expect": "target2.py", "scope": "code", "intent": "retrieval", "top_hit": "target2.py:10"},
    ])

    base_path = tmp_path / "base.json"
    head_path = tmp_path / "head.json"
    base_path.write_text(json.dumps(base))
    head_path.write_text(json.dumps(head))

    old_argv = sys.argv
    try:
        sys.argv = ["diff.py", str(base_path), str(head_path)]
        code = main()
    finally:
        sys.argv = old_argv

    captured = capsys.readouterr().out
    assert "MIXED" in captured
    # The diff.py exit code logic: return 1 if regressed (any regression), else 0
    # With both improvements and regressions, it's MIXED verdict but code=1 (regressed list is non-empty)
    assert code == 1


def test_diff_identical_when_all_stable(tmp_path, capsys):
    """diff classifies verdict as IDENTICAL when all ranks are stable."""
    from hitgate.diff import main

    base = _result([
        {"query": "q1", "hit_rank": 1, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": "target.py:10"},
    ])
    head = _result([
        {"query": "q1", "hit_rank": 1, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": "target.py:10"},
    ])

    base_path = tmp_path / "base.json"
    head_path = tmp_path / "head.json"
    base_path.write_text(json.dumps(base))
    head_path.write_text(json.dumps(head))

    old_argv = sys.argv
    try:
        sys.argv = ["diff.py", str(base_path), str(head_path)]
        code = main()
    finally:
        sys.argv = old_argv

    captured = capsys.readouterr().out
    assert "IDENTICAL" in captured
    assert code == 0


# ---------------------------------------------------------------------------
# rank_val — handling None (MISS)
# ---------------------------------------------------------------------------


def test_diff_rank_val_miss_to_hit():
    """Transition from MISS (None) to a hit (any rank) is an improvement."""
    from hitgate.diff import main

    base = _result([
        {"query": "q1", "hit_rank": None, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": None},
    ])
    head = _result([
        {"query": "q1", "hit_rank": 3, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": "target.py:10"},
    ])

    base_path = Path("/tmp/test_diff_base.json")
    head_path = Path("/tmp/test_diff_head.json")
    base_path.write_text(json.dumps(base))
    head_path.write_text(json.dumps(head))

    try:
        old_argv = sys.argv
        try:
            sys.argv = ["diff.py", str(base_path), str(head_path), "--quiet"]
            code = main()
        finally:
            sys.argv = old_argv
        # Should be improvement (MISS → rank 3)
        assert code == 0
    finally:
        base_path.unlink(missing_ok=True)
        head_path.unlink(missing_ok=True)


def test_diff_rank_val_hit_to_miss():
    """Transition from a hit to MISS (None) is a regression."""
    from hitgate.diff import main

    base = _result([
        {"query": "q1", "hit_rank": 3, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": "target.py:10"},
    ])
    head = _result([
        {"query": "q1", "hit_rank": None, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": None},
    ])

    base_path = Path("/tmp/test_diff_base2.json")
    head_path = Path("/tmp/test_diff_head2.json")
    base_path.write_text(json.dumps(base))
    head_path.write_text(json.dumps(head))

    try:
        old_argv = sys.argv
        try:
            sys.argv = ["diff.py", str(base_path), str(head_path), "--quiet"]
            code = main()
        finally:
            sys.argv = old_argv
        # Should be regression (rank 3 → MISS)
        assert code == 1
    finally:
        base_path.unlink(missing_ok=True)
        head_path.unlink(missing_ok=True)


def test_diff_rank_val_miss_to_miss():
    """MISS → MISS is stable (not a regression)."""
    from hitgate.diff import main

    base = _result([
        {"query": "q1", "hit_rank": None, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": None},
    ])
    head = _result([
        {"query": "q1", "hit_rank": None, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": None},
    ])

    base_path = Path("/tmp/test_diff_base3.json")
    head_path = Path("/tmp/test_diff_head3.json")
    base_path.write_text(json.dumps(base))
    head_path.write_text(json.dumps(head))

    try:
        old_argv = sys.argv
        try:
            sys.argv = ["diff.py", str(base_path), str(head_path), "--quiet"]
            code = main()
        finally:
            sys.argv = old_argv
        # MISS → MISS is stable, not regression
        assert code == 0
    finally:
        base_path.unlink(missing_ok=True)
        head_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Queries present in head but not in baseline
# ---------------------------------------------------------------------------


def test_diff_new_queries_in_head(tmp_path, capsys):
    """diff handles queries present in head but not in baseline gracefully."""
    from hitgate.diff import main

    base = _result([
        {"query": "q1", "hit_rank": 1, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": "target.py:10"},
    ])
    head = _result([
        {"query": "q1", "hit_rank": 1, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": "target.py:10"},
        {"query": "q2", "hit_rank": 2, "expect": "other.py", "scope": "code", "intent": "indexing", "top_hit": "other.py:5"},
    ])

    base_path = tmp_path / "base.json"
    head_path = tmp_path / "head.json"
    base_path.write_text(json.dumps(base))
    head_path.write_text(json.dumps(head))

    old_argv = sys.argv
    try:
        sys.argv = ["diff.py", str(base_path), str(head_path)]
        code = main()
    finally:
        sys.argv = old_argv

    captured = capsys.readouterr().out
    assert "NEW in head" in captured
    # New query in head shouldn't cause a regression verdict
    assert code == 0


# ---------------------------------------------------------------------------
# --quiet flag — summary only
# ---------------------------------------------------------------------------


def test_diff_quiet_suppresses_details(tmp_path, capsys):
    """diff --quiet shows only the summary line, not per-case details."""
    from hitgate.diff import main

    base = _result([
        {"query": "q1", "hit_rank": 1, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": "target.py:10"},
        {"query": "q2", "hit_rank": 5, "expect": "target2.py", "scope": "code", "intent": "retrieval", "top_hit": "other.py:1"},
    ])
    head = _result([
        {"query": "q1", "hit_rank": 5, "expect": "target.py", "scope": "code", "intent": "retrieval", "top_hit": "other.py:1"},
        {"query": "q2", "hit_rank": 1, "expect": "target2.py", "scope": "code", "intent": "retrieval", "top_hit": "target2.py:10"},
    ])

    base_path = tmp_path / "base.json"
    head_path = tmp_path / "head.json"
    base_path.write_text(json.dumps(base))
    head_path.write_text(json.dumps(head))

    old_argv = sys.argv
    try:
        sys.argv = ["diff.py", str(base_path), str(head_path), "--quiet"]
        code = main()
    finally:
        sys.argv = old_argv

    captured = capsys.readouterr().out
    # Should still show the summary line
    assert "verdict" in captured.lower()
    # But NOT the detailed per-case lines
    assert "REGRESSED" not in captured  # would be in verbose output
    assert "IMPROVED" not in captured  # would be in verbose output


# ---------------------------------------------------------------------------
# Missing per_case in results — graceful fallback
# ---------------------------------------------------------------------------


def test_diff_missing_per_case_treats_as_empty(tmp_path, capsys):
    """diff gracefully handles results without per_case array."""
    from hitgate.diff import main

    base = {
        "n": 1,
        "hit@1": 1.0,
        "hit@3": 1.0,
        "hit@5": 1.0,
        "mrr": 1.0,
        # no per_case
    }
    head = {
        "n": 1,
        "hit@1": 0.9,
        "hit@3": 0.9,
        "hit@5": 0.9,
        "mrr": 0.9,
        # no per_case
    }

    base_path = tmp_path / "base.json"
    head_path = tmp_path / "head.json"
    base_path.write_text(json.dumps(base))
    head_path.write_text(json.dumps(head))

    old_argv = sys.argv
    try:
        sys.argv = ["diff.py", str(base_path), str(head_path), "--quiet"]
        code = main()
    finally:
        sys.argv = old_argv

    # Should still produce a summary (even if it's all zeros)
    captured = capsys.readouterr().out
    assert "verdict" in captured.lower()
