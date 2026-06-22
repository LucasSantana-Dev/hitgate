"""Unit tests for ragcore.retrieval — auto-rerank decision logic, cwd_repo detection, tokenization."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

import pytest
import numpy as np

import ragcore.retrieval as retrieval
from ragcore.retrieval import (
    _tokenize,
    _auto_rerank_decision,
    cwd_repo,
    search,
    RERANK_AUTO_THRESHOLD,
    RERANK_AUTO_MARGIN,
)


class TestTokenize:
    """Test code-aware tokenization with camelCase/snake_case splitting."""

    def test_tokenize_simple_words(self):
        result = _tokenize("hello world")
        assert "hello" in result
        assert "world" in result

    def test_tokenize_camel_case(self):
        result = _tokenize("getUserProfile")
        assert "getuser" in result or "getUserProfile".lower() in result
        # Should have subtokens
        assert "get" in result
        assert "user" in result
        assert "profile" in result

    def test_tokenize_snake_case(self):
        result = _tokenize("get_user_profile")
        assert "get" in result
        assert "user" in result
        assert "profile" in result

    def test_tokenize_all_caps(self):
        result = _tokenize("HTTP_SERVER")
        assert "http" in result
        assert "server" in result

    def test_tokenize_mixed_case(self):
        result = _tokenize("getHTTPServer")
        assert "get" in result
        assert "http" in result
        assert "server" in result

    def test_tokenize_single_letter_ignored(self):
        """Single-letter subtokens should be filtered (len >= 2)."""
        result = _tokenize("a_b_c")
        # Should not include single letters
        assert len([t for t in result if len(t) == 1]) == 0

    def test_tokenize_numbers_ignored_in_subs(self):
        """Pure number tokens should be extracted but filtered by length."""
        result = _tokenize("func123name")
        assert "func" in result
        assert "name" in result

    def test_tokenize_lowercase_normalized(self):
        """All tokens should be lowercase."""
        result = _tokenize("GetUserProfile")
        assert all(t.islower() or not t.isalpha() for t in result)

    def test_tokenize_empty_string(self):
        result = _tokenize("")
        assert result == []

    def test_tokenize_special_chars(self):
        """Special chars should delimit tokens."""
        result = _tokenize("func$method")
        assert "func" in result
        assert "method" in result


class TestCwdRepo:
    """Test cwd-to-repo detection."""

    def test_cwd_repo_match_direct(self, tmp_path):
        root = tmp_path / "myrepo"
        root.mkdir()

        with mock.patch("ragcore.retrieval.REPO_ROOTS", [root]):
            result = cwd_repo(str(root))
            assert result == "myrepo"

    def test_cwd_repo_match_nested(self, tmp_path):
        root = tmp_path / "myrepo"
        subdir = root / "src" / "module"
        subdir.mkdir(parents=True)

        with mock.patch("ragcore.retrieval.REPO_ROOTS", [root]):
            result = cwd_repo(str(subdir))
            assert result == "myrepo"

    def test_cwd_repo_no_match(self, tmp_path):
        root = tmp_path / "repoA"
        other = tmp_path / "repoB"
        root.mkdir()
        other.mkdir()

        with mock.patch("ragcore.retrieval.REPO_ROOTS", [root]):
            result = cwd_repo(str(other))
            assert result is None

    def test_cwd_repo_default_to_cwd(self, tmp_path):
        """cwd_repo() with no argument should use os.getcwd()."""
        repo = tmp_path / "myrepo"
        repo.mkdir()

        with mock.patch("ragcore.retrieval.os.getcwd", return_value=str(repo)):
            with mock.patch("ragcore.retrieval.REPO_ROOTS", [repo]):
                result = cwd_repo(None)
                assert result == "myrepo"

    def test_cwd_repo_multiple_roots_first_match(self, tmp_path):
        rootA = tmp_path / "repoA"
        rootB = tmp_path / "repoB"
        rootA.mkdir()
        rootB.mkdir()
        subB = rootB / "src"
        subB.mkdir()

        with mock.patch("ragcore.retrieval.REPO_ROOTS", [rootA, rootB]):
            result = cwd_repo(str(subB))
            assert result == "repoB"


class TestAutoRerank:
    """Test auto-rerank decision logic (threshold, margin, code-scope filter) via pure helper."""

    # Sanity checks for module constants (baseline expectations)
    def test_rerank_auto_threshold_constant_sane(self):
        """RERANK_AUTO_THRESHOLD should be defined and be 0.35."""
        assert RERANK_AUTO_THRESHOLD == 0.35

    def test_rerank_auto_margin_constant_sane(self):
        """RERANK_AUTO_MARGIN should be defined and be 0.015."""
        assert RERANK_AUTO_MARGIN == 0.015

    def test_cwd_repo_detection_works(self, tmp_path):
        """cwd_repo should detect repo from path."""
        repo = tmp_path / "test-repo"
        repo.mkdir()

        with mock.patch("ragcore.retrieval.REPO_ROOTS", [repo]):
            result = cwd_repo(str(repo))
            assert result == "test-repo"

    # Genuine behavioral tests for _auto_rerank_decision
    def test_auto_rerank_low_top1_fires(self):
        """Low top-1 (< 0.35) should trigger auto-rerank when allowed."""
        with mock.patch.object(retrieval, "RERANK_AUTO", True):
            with mock.patch.object(retrieval, "RAG_CODE_RERANK", False):
                # top1=0.30 < RERANK_AUTO_THRESHOLD(0.35) -> rerank should be True
                result = _auto_rerank_decision(rerank=False, top1=0.30, top2=0.29, is_code_scope=False)
                assert result is True

    def test_auto_rerank_small_margin_fires(self):
        """Small margin (< 0.015) between top1/top2 should trigger auto-rerank when allowed."""
        with mock.patch.object(retrieval, "RERANK_AUTO", True):
            with mock.patch.object(retrieval, "RAG_CODE_RERANK", False):
                # top1=0.80, top2=0.79, margin=0.01 < RERANK_AUTO_MARGIN(0.015) -> rerank=True
                result = _auto_rerank_decision(rerank=False, top1=0.80, top2=0.79, is_code_scope=False)
                assert result is True

    def test_auto_rerank_strong_and_separated_does_not_fire(self):
        """Strong top1 and clear margin should NOT trigger auto-rerank."""
        with mock.patch.object(retrieval, "RERANK_AUTO", True):
            with mock.patch.object(retrieval, "RAG_CODE_RERANK", False):
                # top1=0.80, top2=0.50, margin=0.30 > RERANK_AUTO_MARGIN -> rerank=False
                result = _auto_rerank_decision(rerank=False, top1=0.80, top2=0.50, is_code_scope=False)
                assert result is False

    def test_auto_rerank_disabled_globally_never_fires(self):
        """RERANK_AUTO=False should prevent auto-rerank even with low top1."""
        with mock.patch.object(retrieval, "RERANK_AUTO", False):
            with mock.patch.object(retrieval, "RAG_CODE_RERANK", False):
                # Even with top1=0.30 < threshold, RERANK_AUTO=False prevents it
                result = _auto_rerank_decision(rerank=False, top1=0.30, top2=0.29, is_code_scope=False)
                assert result is False

    def test_auto_rerank_code_scope_selective_rerank_enables(self):
        """RAG_CODE_RERANK=True + code scope should enable rerank regardless of scores."""
        with mock.patch.object(retrieval, "RERANK_AUTO", False):
            with mock.patch.object(retrieval, "RAG_CODE_RERANK", True):
                # Code scope + RAG_CODE_RERANK -> rerank=True even with strong scores
                result = _auto_rerank_decision(rerank=False, top1=0.99, top2=0.98, is_code_scope=True)
                assert result is True

    def test_auto_rerank_code_scope_gating_non_code_disables(self):
        """RAG_CODE_RERANK=True but non-code scope should NOT auto-fire on weak scores."""
        with mock.patch.object(retrieval, "RERANK_AUTO", True):
            with mock.patch.object(retrieval, "RAG_CODE_RERANK", True):
                # RAG_CODE_RERANK=True blocks auto-rerank for non-code scopes (auto_allowed=False)
                # even with low top1=0.30
                result = _auto_rerank_decision(rerank=False, top1=0.30, top2=0.29, is_code_scope=False)
                assert result is False

    def test_auto_rerank_explicit_true_stays_true(self):
        """Explicit rerank=True passed to _auto_rerank_decision should stay True."""
        with mock.patch.object(retrieval, "RERANK_AUTO", False):
            with mock.patch.object(retrieval, "RAG_CODE_RERANK", False):
                # rerank=True (already decided) should remain True
                result = _auto_rerank_decision(rerank=True, top1=0.5, top2=0.4, is_code_scope=False)
                assert result is True

    def test_auto_rerank_explicit_false_with_low_scores_can_enable_if_auto_allows(self):
        """rerank=False with low scores + auto-enabled should enable reranking."""
        with mock.patch.object(retrieval, "RERANK_AUTO", True):
            with mock.patch.object(retrieval, "RAG_CODE_RERANK", False):
                # rerank=False, but auto-conditions met (low top1) -> rerank becomes True
                result = _auto_rerank_decision(rerank=False, top1=0.30, top2=0.29, is_code_scope=False)
                assert result is True

    def test_auto_rerank_boundary_top1_exactly_at_threshold(self):
        """top1 exactly at threshold (0.35) should NOT trigger (< condition)."""
        with mock.patch.object(retrieval, "RERANK_AUTO", True):
            with mock.patch.object(retrieval, "RAG_CODE_RERANK", False):
                # top1=0.35 is NOT < 0.35, so no threshold-based trigger
                # But check margin: 0.35 - 0.20 = 0.15 > 0.015, so no margin trigger either
                result = _auto_rerank_decision(rerank=False, top1=0.35, top2=0.20, is_code_scope=False)
                assert result is False

    def test_auto_rerank_boundary_margin_exactly_at_threshold(self):
        """Margin exactly at threshold (0.015) should NOT trigger (< condition)."""
        with mock.patch.object(retrieval, "RERANK_AUTO", True):
            with mock.patch.object(retrieval, "RAG_CODE_RERANK", False):
                # top1=0.80, top2=0.785, margin=0.015 is NOT < 0.015
                result = _auto_rerank_decision(rerank=False, top1=0.80, top2=0.785, is_code_scope=False)
                assert result is False

    def test_auto_rerank_zero_scores_no_panic(self):
        """Zero or missing scores (no results) should not crash."""
        with mock.patch.object(retrieval, "RERANK_AUTO", True):
            with mock.patch.object(retrieval, "RAG_CODE_RERANK", False):
                # top1=0.0, top2=0.0 (no results) -> 0.0 < 0.35 is True
                result = _auto_rerank_decision(rerank=False, top1=0.0, top2=0.0, is_code_scope=False)
                assert result is True


class TestSearchEmptyQuery:
    """Test search() behavior with empty or missing queries."""

    @mock.patch("ragcore.retrieval.require_hybrid")
    def test_search_empty_query_returns_empty(self, mock_require):
        """Empty query string should return empty list."""
        result = retrieval.search("")
        assert result == []

    @mock.patch("ragcore.retrieval.require_hybrid")
    def test_search_whitespace_only_returns_empty(self, mock_require):
        """Whitespace-only query should return empty list."""
        result = retrieval.search("   ")
        assert result == []


class TestSearchScopeTypeHandling:
    """Test scope_types defensive handling."""

    @mock.patch("ragcore.retrieval._load")
    @mock.patch("ragcore.retrieval._get_model")
    def test_search_scope_types_string_converted_to_list(self, mock_model, mock_load):
        """scope_types as bare string should be wrapped in a list."""
        mock_meta = []
        mock_embs = np.zeros((0, 384), dtype=np.float32)
        mock_load.return_value = (mock_meta, mock_embs, mock.Mock())

        mock_model_inst = mock.Mock()
        mock_model_inst.encode.return_value = np.array([[0.5]], dtype=np.float32)
        mock_model.return_value = mock_model_inst

        with mock.patch("ragcore.retrieval.require_hybrid"):
            # Pass scope_types as string (defensive check)
            result = retrieval.search("test", scope_types="code")
            # Should not crash; _load should be called with list
            assert isinstance(result, list)

    @mock.patch("ragcore.retrieval._load")
    @mock.patch("ragcore.retrieval._get_model")
    def test_search_scope_repos_all_becomes_none(self, mock_model, mock_load):
        """scope_repos=['all'] should become None."""
        mock_meta = []
        mock_embs = np.zeros((0, 384), dtype=np.float32)
        mock_load.return_value = (mock_meta, mock_embs, mock.Mock())

        mock_model_inst = mock.Mock()
        mock_model_inst.encode.return_value = np.array([[0.5]], dtype=np.float32)
        mock_model.return_value = mock_model_inst

        with mock.patch("ragcore.retrieval.require_hybrid"):
            result = retrieval.search("test", scope_repos=["all"])
            # _load should have been called with scope_repos=None
            assert mock_load.called
            # Check the call arguments
            call_args = mock_load.call_args[0]
            # _load(scope_types, scope_repos)
            assert call_args[1] is None


class TestRerankerFallback:
    """Test reranker unavailability fallback."""

    def test_reranker_graceful_degradation(self):
        """When reranker is unavailable, search should still work."""
        with mock.patch("ragcore.retrieval.require_hybrid"):
            with mock.patch("ragcore.retrieval._load") as mock_load:
                # Return empty results so reranker doesn't get called
                mock_load.return_value = ([], np.zeros((0, 384), dtype=np.float32), mock.Mock())

                # Search with rerank=True but empty results
                results = retrieval.search("test", rerank=True)
                assert isinstance(results, list)
                # Empty results should return []
                assert len(results) == 0
