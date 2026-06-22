"""Shared test fixtures. Sets RAG_* env BEFORE ragcore.config is imported so the index
resolves into a throwaway dir, then builds a tiny real index (real e5 + BM25)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_TMP = Path(tempfile.mkdtemp(prefix="efr-tests-"))

# Must run before any ragcore import (config reads these at import time).
os.environ.setdefault("RAG_INDEX_DIR", str(_TMP / ".rag-index"))
os.environ.setdefault("RAG_SOURCE_ROOTS", str(_TMP / "corpus"))
os.environ.setdefault("RAG_RERANK_AUTO", "off")
os.environ.setdefault("RAG_QLOG", "off")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def tiny_index():
    """A 3-file code index built with real embeddings + BM25, in a throwaway dir."""
    corpus = _TMP / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    (corpus / "fusion.py").write_text(
        "def reciprocal_rank_fusion(dense_order, bm25_order):\n"
        "    '''Fuse two ranked lists by reciprocal rank.'''\n"
        "    return merged\n"
    )
    (corpus / "tokenizer.py").write_text(
        "def split_camel_case_identifier(name):\n"
        "    '''Split getUserProfile into get, user, profile subtokens.'''\n"
        "    return parts\n"
    )
    (corpus / "settings.py").write_text(
        "DATABASE_CONNECTION_STRING = 'sqlite:///x'  # environment configuration default\n"
    )
    # build.py indexes recent git commits too; make the corpus a repo so that path is clean.
    env = {**os.environ}
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"]):
        subprocess.run(cmd, cwd=str(corpus), env=env, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed"],
        cwd=str(corpus), env=env, capture_output=True,
    )
    r = subprocess.run(
        [sys.executable, str(ROOT / "ragcore" / "build.py")],
        cwd=str(corpus), env=env, capture_output=True, text=True,
    )
    if r.returncode != 0:
        pytest.skip(f"could not build test index (model unavailable offline?): {r.stderr[-300:]}")
    return _TMP
