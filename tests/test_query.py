"""Unit tests for ragcore.query — CLI arg parsing, output formats, exit codes."""
from __future__ import annotations

import json
import sys
from unittest import mock
from io import StringIO

import pytest

from ragcore.query import main


class TestQueryArgumentParsing:
    """Test CLI argument parsing and scope handling."""

    def test_query_required_argument(self):
        """Query positional argument is required."""
        with mock.patch.object(sys, "argv", ["query.py"]):
            with pytest.raises(SystemExit):
                main()

    def test_query_simple(self, capsys, monkeypatch):
        """Basic query with defaults."""
        with mock.patch("ragcore.query.search") as mock_search:
            mock_search.return_value = []
            with mock.patch.object(
                sys, "argv", ["query.py", "test query"]
            ):
                result = main()
                assert result == 1  # No results
                mock_search.assert_called_once()
                call_args = mock_search.call_args
                assert call_args[0][0] == "test query"

    def test_scope_comma_separated(self, monkeypatch):
        """--scope with comma-separated types."""
        with mock.patch("ragcore.query.search") as mock_search:
            mock_search.return_value = []
            with mock.patch.object(
                sys, "argv", ["query.py", "--scope", "code,memory", "test"]
            ):
                main()
                call_kwargs = mock_search.call_args[1]
                assert call_kwargs["scope_types"] == ["code", "memory"]

    def test_scope_with_whitespace(self, monkeypatch):
        """--scope should strip whitespace."""
        with mock.patch("ragcore.query.search") as mock_search:
            mock_search.return_value = []
            with mock.patch.object(
                sys, "argv", ["query.py", "--scope", " code , docs ", "test"]
            ):
                main()
                call_kwargs = mock_search.call_args[1]
                assert call_kwargs["scope_types"] == ["code", "docs"]

    def test_scope_empty_string_becomes_none(self, monkeypatch):
        """Empty --scope should result in None."""
        with mock.patch("ragcore.query.search") as mock_search:
            mock_search.return_value = []
            with mock.patch.object(
                sys, "argv", ["query.py", "--scope", "", "test"]
            ):
                main()
                call_kwargs = mock_search.call_args[1]
                assert call_kwargs["scope_types"] is None

    def test_scope_repo_all(self, monkeypatch):
        """--scope-repo all should disable cwd scoping."""
        with mock.patch("ragcore.query.search") as mock_search:
            mock_search.return_value = []
            with mock.patch.object(
                sys, "argv", ["query.py", "--scope-repo", "all", "test"]
            ):
                main()
                call_kwargs = mock_search.call_args[1]
                assert call_kwargs["scope_repos"] is None
                assert call_kwargs["cwd"] is None

    def test_scope_repo_comma_separated(self, monkeypatch):
        """--scope-repo with comma-separated repos."""
        with mock.patch("ragcore.query.search") as mock_search:
            mock_search.return_value = []
            with mock.patch.object(
                sys, "argv", ["query.py", "--scope-repo", "repoA,repoB", "test"]
            ):
                main()
                call_kwargs = mock_search.call_args[1]
                assert call_kwargs["scope_repos"] == ["repoA", "repoB"]

    def test_scope_repo_default_uses_cwd(self, monkeypatch):
        """Default --scope-repo should auto-detect via cwd_repo()."""
        with mock.patch("ragcore.query.search") as mock_search:
            mock_search.return_value = []
            with mock.patch.object(sys, "argv", ["query.py", "test"]):
                main()
                call_kwargs = mock_search.call_args[1]
                # cwd should be None to trigger cwd_repo detection
                assert call_kwargs["cwd"] is None
                assert call_kwargs["scope_repos"] is None


class TestQueryReranking:
    """Test --rerank flag behavior."""

    def test_rerank_on(self, monkeypatch):
        """--rerank on should force rerank=True."""
        with mock.patch("ragcore.query.search") as mock_search:
            mock_search.return_value = []
            with mock.patch.object(
                sys, "argv", ["query.py", "--rerank", "on", "test"]
            ):
                main()
                call_kwargs = mock_search.call_args[1]
                assert call_kwargs["rerank"] is True

    def test_rerank_off(self, monkeypatch):
        """--rerank off should force rerank=False."""
        with mock.patch("ragcore.query.search") as mock_search:
            mock_search.return_value = []
            with mock.patch.object(
                sys, "argv", ["query.py", "--rerank", "off", "test"]
            ):
                main()
                call_kwargs = mock_search.call_args[1]
                assert call_kwargs["rerank"] is False

    def test_rerank_auto_default(self, monkeypatch):
        """--rerank auto should default to True (but can be overridden by env)."""
        with mock.patch("ragcore.query.search") as mock_search:
            mock_search.return_value = []
            with mock.patch.object(
                sys, "argv", ["query.py", "--rerank", "auto", "test"]
            ):
                main()
                call_kwargs = mock_search.call_args[1]
                # auto defaults to True in the call
                assert call_kwargs["rerank"] is True

    def test_fast_disables_rerank(self, monkeypatch):
        """--fast should disable reranking even if default is auto."""
        with mock.patch("ragcore.query.search") as mock_search:
            mock_search.return_value = []
            with mock.patch.object(
                sys, "argv", ["query.py", "--fast", "test"]
            ):
                main()
                call_kwargs = mock_search.call_args[1]
                assert call_kwargs["rerank"] is False

    def test_rerank_off_takes_precedence_over_fast(self, monkeypatch):
        """--rerank off should win even with --fast implied."""
        with mock.patch("ragcore.query.search") as mock_search:
            mock_search.return_value = []
            with mock.patch.object(
                sys, "argv", ["query.py", "--rerank", "off", "--fast", "test"]
            ):
                main()
                call_kwargs = mock_search.call_args[1]
                assert call_kwargs["rerank"] is False


class TestQueryOutputFormats:
    """Test output format handling (text vs JSON)."""

    def test_json_output_format(self, capsys, monkeypatch):
        """--format json should output valid JSON."""
        mock_results = [
            {
                "rank": 1,
                "rrf": 0.95,
                "cos": 0.9,
                "bm25": 10.0,
                "reranked": False,
                "source_type": "code",
                "repo": "test-repo",
                "language": "python",
                "symbol": "func",
                "path": "/path/to/file.py",
                "start_line": 1,
                "end_line": 10,
                "text": "def func(): pass",
            }
        ]

        with mock.patch("ragcore.query.search", return_value=mock_results):
            with mock.patch.object(
                sys, "argv", ["query.py", "--format", "json", "test"]
            ):
                result = main()
                assert result == 0
                captured = capsys.readouterr()
                output = json.loads(captured.out)
                assert len(output) == 1
                assert output[0]["rank"] == 1
                assert output[0]["symbol"] == "func"

    def test_text_output_format(self, capsys, monkeypatch):
        """--format text should print human-readable output."""
        mock_results = [
            {
                "rank": 1,
                "rrf": 0.95,
                "cos": 0.9,
                "bm25": 10.0,
                "reranked": False,
                "source_type": "code",
                "repo": "test-repo",
                "language": "python",
                "symbol": "search",
                "path": "/path/to/retrieval.py",
                "start_line": 186,
                "end_line": 220,
                "text": "def search(query): return results",
            }
        ]

        with mock.patch("ragcore.query.search", return_value=mock_results):
            with mock.patch.object(
                sys, "argv", ["query.py", "--format", "text", "test"]
            ):
                result = main()
                assert result == 0
                captured = capsys.readouterr()
                output = captured.out
                assert "#1" in output  # rank marker
                assert "code/test-repo::search" in output  # tag
                assert "retrieval.py:186-220" in output  # path
                assert "def search" in output  # snippet


class TestQueryExitCodes:
    """Test exit code behavior."""

    def test_no_results_exit_1(self, monkeypatch):
        """No results should exit with code 1."""
        with mock.patch("ragcore.query.search", return_value=[]):
            with mock.patch.object(sys, "argv", ["query.py", "test"]):
                result = main()
                assert result == 1

    def test_results_exit_0(self, monkeypatch):
        """With results, should exit with code 0."""
        mock_results = [
            {
                "rank": 1,
                "rrf": 0.95,
                "cos": 0.9,
                "bm25": 10.0,
                "reranked": False,
                "source_type": "code",
                "repo": "test-repo",
                "language": "python",
                "symbol": "func",
                "path": "/path/to/file.py",
                "start_line": 1,
                "end_line": 10,
                "text": "def func(): pass",
            }
        ]

        with mock.patch("ragcore.query.search", return_value=mock_results):
            with mock.patch.object(sys, "argv", ["query.py", "test"]):
                result = main()
                assert result == 0

    def test_json_format_exit_0_even_empty(self, monkeypatch):
        """JSON format should exit 0 even with no results."""
        with mock.patch("ragcore.query.search", return_value=[]):
            with mock.patch.object(
                sys, "argv", ["query.py", "--format", "json", "test"]
            ):
                result = main()
                assert result == 0  # JSON succeeds even with empty array


class TestQueryTopParameter:
    """Test --top parameter."""

    def test_top_default_is_5(self, monkeypatch):
        """Default --top should be 5."""
        with mock.patch("ragcore.query.search") as mock_search:
            mock_search.return_value = []
            with mock.patch.object(sys, "argv", ["query.py", "test"]):
                main()
                call_kwargs = mock_search.call_args[1]
                assert call_kwargs["top"] == 5

    def test_top_custom_value(self, monkeypatch):
        """--top should accept custom values."""
        with mock.patch("ragcore.query.search") as mock_search:
            mock_search.return_value = []
            with mock.patch.object(sys, "argv", ["query.py", "--top", "10", "test"]):
                main()
                call_kwargs = mock_search.call_args[1]
                assert call_kwargs["top"] == 10

    def test_top_string_conversion(self, monkeypatch):
        """--top should convert string to int."""
        with mock.patch("ragcore.query.search") as mock_search:
            mock_search.return_value = []
            with mock.patch.object(sys, "argv", ["query.py", "--top", "3", "test"]):
                main()
                call_kwargs = mock_search.call_args[1]
                assert call_kwargs["top"] == 3
                assert isinstance(call_kwargs["top"], int)


class TestQueryTextOutput:
    """Test text output formatting details."""

    def test_text_output_no_results_message(self, capsys, monkeypatch):
        """Text output should show '(no matches)' when no results."""
        with mock.patch("ragcore.query.search", return_value=[]):
            with mock.patch.object(sys, "argv", ["query.py", "test"]):
                main()
                captured = capsys.readouterr()
                assert "(no matches)" in captured.out

    def test_text_output_truncates_long_snippets(self, capsys, monkeypatch):
        """Text output should truncate snippets > 400 chars."""
        mock_results = [
            {
                "rank": 1,
                "rrf": 0.95,
                "cos": 0.9,
                "bm25": 10.0,
                "reranked": False,
                "source_type": "code",
                "repo": "test-repo",
                "language": "python",
                "symbol": "func",
                "path": "/path/to/file.py",
                "start_line": 1,
                "end_line": 100,
                "text": "x" * 500,  # 500 chars
            }
        ]

        with mock.patch("ragcore.query.search", return_value=mock_results):
            with mock.patch.object(sys, "argv", ["query.py", "test"]):
                main()
                captured = capsys.readouterr()
                # Should have ellipsis for truncation
                assert "…" in captured.out

    def test_text_output_format_defaults_to_text(self, capsys, monkeypatch):
        """--format should default to text."""
        mock_results = [
            {
                "rank": 1,
                "rrf": 0.95,
                "cos": 0.9,
                "bm25": 10.0,
                "reranked": False,
                "source_type": "code",
                "repo": "repo",
                "language": "python",
                "symbol": None,
                "path": "/file.py",
                "start_line": 1,
                "end_line": 10,
                "text": "code",
            }
        ]

        with mock.patch("ragcore.query.search", return_value=mock_results):
            with mock.patch.object(sys, "argv", ["query.py", "test"]):
                main()
                captured = capsys.readouterr()
                # Text format should have rank marker
                assert "#1" in captured.out
                # Not JSON
                assert "{" not in captured.out or "[" not in captured.out
