"""Tests for hitgate/scaffold.py — the `hitgate-init` / `hitgate-demo` onboarding commands.

These exercise orchestration + I/O behaviour (root resolution, scaffold write,
idempotency, empty-corpus handling, and the [hybrid] guard). The end-to-end demo
(index build + bundled retriever) is not exercised here — it needs a model download.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from hitgate import scaffold


SAMPLE_PY = '''\
def calculate_invoice_total(items, tax_rate):
    """Compute the total invoice amount including tax for a list of line items."""
    subtotal = sum(item.price for item in items)
    return subtotal * (1 + tax_rate)


def normalize_currency_code(raw_code):
    """Return the ISO 4217 uppercase currency code for a loosely-formatted input."""
    return raw_code.strip().upper()
'''


# ---------------------------------------------------------------------------
# _resolve_root — precedence: arg > $RAG_SOURCE_ROOTS > cwd
# ---------------------------------------------------------------------------

def test_resolve_root_explicit_arg_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_SOURCE_ROOTS", str(tmp_path / "from_env"))
    got = scaffold._resolve_root(str(tmp_path / "from_arg"))
    assert got == (tmp_path / "from_arg").resolve()


def test_resolve_root_falls_back_to_env_first_entry(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    import os
    monkeypatch.setenv("RAG_SOURCE_ROOTS", f"{a}{os.pathsep}{b}")
    assert scaffold._resolve_root(None) == a.resolve()


def test_resolve_root_falls_back_to_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("RAG_SOURCE_ROOTS", raising=False)
    monkeypatch.chdir(tmp_path)
    assert scaffold._resolve_root(None) == Path.cwd()


# ---------------------------------------------------------------------------
# init — scaffold a golden set
# ---------------------------------------------------------------------------

def test_init_writes_golden_set(tmp_path):
    (tmp_path / "billing.py").write_text(SAMPLE_PY)
    out = tmp_path / "eval" / "golden.jsonl"

    code = scaffold.init(tmp_path, out, min_confidence="low")

    assert code == 0
    assert out.is_file()
    lines = [json.loads(ln) for ln in out.read_text().splitlines() if ln.strip()]
    assert lines, "expected at least one candidate case"
    # Only the harness fields are serialised (no _symbol/_confidence helpers)
    for case in lines:
        assert "query" in case and "expect_path_contains" in case
        assert not any(k.startswith("_") for k in case)


def test_init_is_idempotent_and_does_not_clobber(tmp_path, capsys):
    out = tmp_path / "eval" / "golden.jsonl"
    out.parent.mkdir(parents=True)
    sentinel = '{"query": "curated by hand", "expect_path_contains": "x.py"}\n'
    out.write_text(sentinel)

    code = scaffold.init(tmp_path, out)

    assert code == 0
    assert out.read_text() == sentinel  # untouched
    assert "already exists" in capsys.readouterr().out


def test_init_no_candidates_returns_1(tmp_path, capsys):
    # An empty corpus (no source files) yields nothing to scaffold.
    out = tmp_path / "eval" / "golden.jsonl"
    code = scaffold.init(tmp_path, out)
    assert code == 1
    assert not out.exists()
    assert "No candidate cases" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# demo — [hybrid] guard
# ---------------------------------------------------------------------------

def test_demo_without_hybrid_engine_returns_1(tmp_path, monkeypatch, capsys):
    # Simulate the [hybrid] extra being absent: a None entry makes the import raise.
    monkeypatch.setitem(sys.modules, "ragcore.retrieval", None)
    code = scaffold.demo(tmp_path)
    assert code == 1
    assert "hitgate[hybrid]" in capsys.readouterr().err
