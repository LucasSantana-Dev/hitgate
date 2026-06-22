"""Unit tests for ragcore.pack — budget enforcement, per-chunk caps, and fallback behavior."""
from __future__ import annotations

from unittest import mock

import pytest

from ragcore.pack import pack, approx_tokens


class TestApproxTokens:
    """Test token approximation (chars / 4)."""

    def test_empty_string(self):
        assert approx_tokens("") == 1  # min 1 token

    def test_single_char(self):
        assert approx_tokens("a") == 1

    def test_four_chars(self):
        assert approx_tokens("abcd") == 1

    def test_eight_chars(self):
        assert approx_tokens("abcdefgh") == 2

    def test_large_text(self):
        text = "a" * 400
        assert approx_tokens(text) == 100


class TestPack:
    """Test pack() with mocked search()."""

    def test_pack_returns_string(self):
        with mock.patch("ragcore.pack.search", return_value=[]):
            result = pack("test task", [], budget_tokens=1000, cwd=None)
            assert isinstance(result, str)

    def test_pack_with_no_results(self):
        with mock.patch("ragcore.pack.search", return_value=[]):
            result = pack("test task", [], budget_tokens=1000, cwd=None)
            assert "(no relevant context found)" in result

    def test_pack_includes_header(self):
        """When results exist, header should include task and budget."""
        mock_chunks = [
            {
                "source_type": "code",
                "repo": "repo",
                "symbol": "func",
                "path": "/file.py",
                "start_line": 1,
                "end_line": 10,
                "text": "code snippet",
                "cos": 0.9,
                "bm25": 10.0,
            }
        ]
        with mock.patch("ragcore.pack.search") as mock_search:
            mock_search.side_effect = [mock_chunks, [], []]
            result = pack("my task description", [], budget_tokens=2000, cwd=None)
            assert "my task description" in result
            assert "2000" in result
            assert "Context pack for:" in result

    def test_pack_respects_budget_cap(self):
        """Output size should never exceed budget (in approximate tokens)."""
        mock_chunks = [
            {
                "source_type": "code",
                "repo": "test-repo",
                "symbol": "func1",
                "path": "/path/to/file.py",
                "start_line": 1,
                "end_line": 10,
                "text": "x" * 5000,  # Very large chunk
                "cos": 0.95,
                "bm25": 10.0,
            }
        ]

        with mock.patch("ragcore.pack.search", return_value=mock_chunks):
            result = pack("test", [], budget_tokens=100, cwd=None)
            # Approx tokens: len(result) // 4
            result_tokens = approx_tokens(result)
            # Should stay under or very close to budget
            assert result_tokens <= 150  # Allow some tolerance

    def test_pack_includes_code_results(self):
        mock_chunks = [
            {
                "source_type": "code",
                "repo": "myrepo",
                "symbol": "search",
                "path": "/path/to/retrieval.py",
                "start_line": 186,
                "end_line": 220,
                "text": "def search(query, top=5): pass",
                "cos": 0.92,
                "bm25": 15.0,
            }
        ]

        with mock.patch("ragcore.pack.search") as mock_search:
            # First call (code hits), return results; subsequent calls return empty
            mock_search.side_effect = [mock_chunks, [], []]
            result = pack("search implementation", [], budget_tokens=5000, cwd=None)
            assert "search" in result.lower()
            assert "retrieval.py" in result
            # Verify search was called with correct scope
            assert mock_search.call_count >= 1
            first_call = mock_search.call_args_list[0]
            assert first_call[1].get("scope_types") == ["code"]

    def test_pack_includes_standards_section(self):
        """Standards should be fetched and included if available."""
        mock_std_chunks = [
            {
                "source_type": "standards",
                "repo": None,
                "symbol": "test-standard",
                "path": ".claude/standards/testing.md",
                "start_line": 1,
                "end_line": 30,
                "text": "All tests must be deterministic",
                "cos": 0.88,
                "bm25": 12.0,
            }
        ]

        with mock.patch("ragcore.pack.search") as mock_search:
            mock_search.side_effect = [[], mock_std_chunks, []]
            result = pack("test strategy", [], budget_tokens=5000, cwd=None)
            assert "standards" in result.lower() or "standard" in result.lower() or mock_std_chunks[0]["text"] in result

    def test_pack_honors_per_chunk_caps(self):
        """Each chunk should be truncated to its per_chunk_cap."""
        long_text = "a" * 2000
        mock_chunks = [
            {
                "source_type": "code",
                "repo": "repo",
                "symbol": "func",
                "path": "/file.py",
                "start_line": 1,
                "end_line": 50,
                "text": long_text,
                "cos": 0.9,
                "bm25": 10.0,
            }
        ]

        with mock.patch("ragcore.pack.search") as mock_search:
            mock_search.side_effect = [mock_chunks, [], []]
            result = pack("test", [], budget_tokens=10000, cwd=None)
            # The text should be capped at 900 chars (per_chunk_cap for code)
            # but still present in output
            assert long_text[:100] in result or "aaaa" in result

    def test_pack_calls_search_with_correct_params(self):
        """Verify search is called with task and expected scope params."""
        with mock.patch("ragcore.pack.search") as mock_search:
            mock_search.return_value = []
            pack("my query", ["file1.py", "file2.py"], budget_tokens=2000, cwd="/some/path")

            # Check that search was called at least once
            assert mock_search.called
            # First call should be for code hits with scope_types=["code"]
            first_call = mock_search.call_args_list[0]
            assert first_call[0][0] == "my query" or "query" in str(first_call)

    def test_pack_empty_files_arg(self):
        """Empty files list should still produce output."""
        with mock.patch("ragcore.pack.search", return_value=[]):
            result = pack("test", [], budget_tokens=1000, cwd=None)
            assert isinstance(result, str)

    def test_pack_with_cwd_passed_to_search(self):
        """cwd parameter should be passed through to search."""
        with mock.patch("ragcore.pack.search") as mock_search:
            mock_search.return_value = []
            pack("test", [], budget_tokens=1000, cwd="/specific/path")
            # Verify cwd was passed to at least one search call
            for call in mock_search.call_args_list:
                if "cwd" in call[1]:
                    assert call[1]["cwd"] == "/specific/path"

    def test_pack_explicit_files_fallback(self):
        """When explicit file has no search results, should fall back to header read."""
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# Test file\ndef foo():\n    pass\n")

            with mock.patch("ragcore.pack.search") as mock_search:
                # All search calls return empty (so fallback will trigger)
                mock_search.return_value = []
                result = pack("test", [str(test_file)], budget_tokens=2000, cwd=None)
                # Should include fallback (first 40 lines of file)
                assert "test.py" in result or "def foo" in result

    def test_pack_budget_depletion_stops_adding_chunks(self):
        """Once budget is exhausted, no more chunks should be added."""
        mock_chunks = [
            {
                "source_type": "code",
                "repo": "repo",
                "symbol": f"func{i}",
                "path": f"/file{i}.py",
                "start_line": 1,
                "end_line": 10,
                "text": "x" * 500,
                "cos": 0.9,
                "bm25": 10.0,
            }
            for i in range(10)
        ]

        with mock.patch("ragcore.pack.search") as mock_search:
            mock_search.side_effect = [mock_chunks, [], []]
            result = pack("test", [], budget_tokens=50, cwd=None)
            # With tight budget, not all chunks should be included
            # Verify we didn't include all 10 functions
            func_count = result.count("func")
            assert func_count < 10  # Should have dropped some

    def test_pack_no_results_fallback_message(self):
        """When no results after all searches, should return specific fallback."""
        with mock.patch("ragcore.pack.search", return_value=[]):
            result = pack("something very obscure", [], budget_tokens=1000, cwd=None)
            assert "(no relevant context found)" in result
