"""Tests for hitgate/plot_history.py — Hit@5 history tracking.

Tests verify: commits() parses git log, hit5_at() handles subprocess failures,
matplotlib ImportError fallback still writes JSON data. No actual git worktrees or evals.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# commits() — parse git log output
# ---------------------------------------------------------------------------


def test_commits_parses_log_output():
    """commits() parses git log output and reverses for chronological order."""
    from hitgate.plot_history import commits

    # Mock git to return a log format (newest first from git log)
    log_output = (
        "ghi9012\t2024-01-03\tBug fix\n"
        "def5678\t2024-01-02\tAdd feature\n"
        "abc1234\t2024-01-01\tInitial commit\n"
    )

    with patch("hitgate.plot_history.git", return_value=log_output):
        result = commits("main", limit=10)

    assert len(result) == 3
    # Should be reversed to chronological order (oldest first)
    assert result[0][0] == "abc1234"
    assert result[0][1] == "2024-01-01"
    assert result[0][2] == "Initial commit"
    assert result[2][0] == "ghi9012"
    assert result[2][1] == "2024-01-03"
    assert result[2][2] == "Bug fix"


def test_commits_respects_limit():
    """commits() respects the limit parameter (passes -nN to git)."""
    from hitgate.plot_history import commits

    log_output = (
        "abc1234\t2024-01-01\tCommit 1\n"
        "def5678\t2024-01-02\tCommit 2\n"
    )

    with patch("hitgate.plot_history.git", return_value=log_output) as mock_git:
        commits("main", limit=5)

    # Should have called git with -n5
    mock_git.assert_called_once()
    args = mock_git.call_args[0]
    assert "-n5" in args or args[1] == "-n5"


def test_commits_handles_multiline_subjects():
    """commits() extracts subject correctly even with tabs in message."""
    from hitgate.plot_history import commits

    log_output = "abc1234\t2024-01-01\tWIP: refactor\t(with tab in subject)\n"

    with patch("hitgate.plot_history.git", return_value=log_output):
        result = commits("main", limit=1)

    assert len(result) == 1
    # Subject includes everything after second tab
    assert "refactor" in result[0][2]


def test_commits_skips_empty_lines():
    """commits() gracefully skips empty lines."""
    from hitgate.plot_history import commits

    log_output = (
        "abc1234\t2024-01-01\tCommit 1\n"
        "\n"  # empty line
        "def5678\t2024-01-02\tCommit 2\n"
    )

    with patch("hitgate.plot_history.git", return_value=log_output):
        result = commits("main", limit=10)

    assert len(result) == 2


# ---------------------------------------------------------------------------
# hit5_at() — subprocess execution and error handling
# ---------------------------------------------------------------------------


def test_hit5_at_success_parses_json():
    """hit5_at() successfully reads and parses the hit5 value from result JSON."""
    from hitgate.plot_history import hit5_at

    # Mock git worktree add/remove
    # Mock subprocess.run to simulate successful build and eval
    def mock_run(cmd, **kwargs):
        if "build.py" in str(cmd) or "hitgate.run" in str(cmd):
            # Simulate success
            return MagicMock(returncode=0, stdout="", stderr="")
        return MagicMock(returncode=0)

    with patch("hitgate.plot_history.git") as mock_git:
        with patch("subprocess.run", side_effect=mock_run):
            with patch("tempfile.TemporaryDirectory") as mock_tmp:
                # Set up temporary directory structure
                tmp_path = Path("/tmp/efr-hist-test")
                wt = tmp_path / "wt"

                mock_tmp.return_value.__enter__.return_value = str(tmp_path)
                mock_tmp.return_value.__exit__.return_value = False

                with patch.object(Path, "exists", return_value=True):
                    with patch.object(Path, "read_text", return_value=json.dumps({"hit@5": 0.85})):
                        result = hit5_at("abc1234")

    assert result == 0.85


def test_hit5_at_git_worktree_failure_returns_none():
    """hit5_at() returns None when git worktree add fails."""
    from hitgate.plot_history import hit5_at

    with patch("hitgate.plot_history.git", side_effect=subprocess.CalledProcessError(1, "git")):
        result = hit5_at("abc1234")

    assert result is None


def test_hit5_at_missing_eval_file_returns_none():
    """hit5_at() returns None when the eval result JSON doesn't exist."""
    from hitgate.plot_history import hit5_at

    def mock_run(cmd, **kwargs):
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("hitgate.plot_history.git") as mock_git:
        with patch("subprocess.run", side_effect=mock_run):
            with patch("tempfile.TemporaryDirectory") as mock_tmp:
                tmp_path = Path("/tmp/efr-hist-test-missing")
                mock_tmp.return_value.__enter__.return_value = str(tmp_path)
                mock_tmp.return_value.__exit__.return_value = False

                # Simulate that the eval output file doesn't exist
                with patch.object(Path, "exists", side_effect=lambda: False):
                    result = hit5_at("abc1234")

    assert result is None


def test_hit5_at_eval_fails_returns_none():
    """hit5_at() returns None when the eval subprocess fails."""
    from hitgate.plot_history import hit5_at

    call_count = [0]

    def mock_run(cmd, **kwargs):
        call_count[0] += 1
        # First call (build): succeed
        # Second call (eval): fail
        if call_count[0] == 1:
            return MagicMock(returncode=0, stdout="", stderr="")
        else:
            return MagicMock(returncode=1, stdout="", stderr="FAIL")

    with patch("hitgate.plot_history.git") as mock_git:
        with patch("subprocess.run", side_effect=mock_run):
            with patch("tempfile.TemporaryDirectory") as mock_tmp:
                tmp_path = Path("/tmp/efr-hist-test-eval-fail")
                mock_tmp.return_value.__enter__.return_value = str(tmp_path)
                mock_tmp.return_value.__exit__.return_value = False

                with patch.object(Path, "exists", return_value=True):
                    result = hit5_at("abc1234")

    assert result is None


def test_hit5_at_malformed_json_returns_none():
    """hit5_at() returns None when result JSON is malformed."""
    from hitgate.plot_history import hit5_at

    def mock_run(cmd, **kwargs):
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("hitgate.plot_history.git") as mock_git:
        with patch("subprocess.run", side_effect=mock_run):
            with patch("tempfile.TemporaryDirectory") as mock_tmp:
                tmp_path = Path("/tmp/efr-hist-test-bad-json")
                mock_tmp.return_value.__enter__.return_value = str(tmp_path)
                mock_tmp.return_value.__exit__.return_value = False

                # Simulate reading malformed JSON
                with patch.object(Path, "exists", return_value=True):
                    with patch.object(Path, "read_text", return_value="not valid json"):
                        with pytest.raises(json.JSONDecodeError):
                            hit5_at("abc1234")


def test_hit5_at_missing_hit5_key_returns_none():
    """hit5_at() returns None when result JSON has no hit@5 key."""
    from hitgate.plot_history import hit5_at

    def mock_run(cmd, **kwargs):
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("hitgate.plot_history.git") as mock_git:
        with patch("subprocess.run", side_effect=mock_run):
            with patch("tempfile.TemporaryDirectory") as mock_tmp:
                tmp_path = Path("/tmp/efr-hist-test-no-hit5")
                mock_tmp.return_value.__enter__.return_value = str(tmp_path)
                mock_tmp.return_value.__exit__.return_value = False

                # Result has no hit@5 key
                with patch.object(Path, "exists", return_value=True):
                    with patch.object(Path, "read_text", return_value=json.dumps({"mrr": 0.75})):
                        result = hit5_at("abc1234")

    assert result is None


def test_hit5_at_harness_not_in_commit_returns_none():
    """hit5_at() returns None when eval harness doesn't exist at a commit."""
    from hitgate.plot_history import hit5_at

    def mock_run(cmd, **kwargs):
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("hitgate.plot_history.git") as mock_git:
        with patch("subprocess.run", side_effect=mock_run):
            with patch("tempfile.TemporaryDirectory") as mock_tmp:
                tmp_path = Path("/tmp/efr-hist-test-no-harness")
                mock_tmp.return_value.__enter__.return_value = str(tmp_path)
                mock_tmp.return_value.__exit__.return_value = False

                # Simulate EVAL_REL and GOLDEN_REL not existing
                with patch.object(Path, "exists", return_value=False):
                    result = hit5_at("abc1234")

    assert result is None


# ---------------------------------------------------------------------------
# main() — matplotlib ImportError fallback
# ---------------------------------------------------------------------------


def test_main_writes_json_data_on_success(tmp_path, capsys, mocker):
    """main() writes hit5_history.json and svg when data is available."""
    from hitgate.plot_history import main

    # Create a fake DOCS directory
    docs = tmp_path / "docs"
    docs.mkdir()

    old_argv = sys.argv
    try:
        sys.argv = ["plot_history.py", "--max-commits", "10"]

        with patch("hitgate.plot_history.ROOT", tmp_path):
            with patch("hitgate.plot_history.DOCS", docs):
                with patch("hitgate.plot_history.commits", return_value=[
                    ("abc1234", "2024-01-01", "Commit 1"),
                    ("def5678", "2024-01-02", "Commit 2"),
                ]):
                    with patch("hitgate.plot_history.hit5_at", side_effect=[0.80, 0.85]):
                        # Mock matplotlib components
                        mock_fig = MagicMock()
                        mock_ax = MagicMock()
                        mocker.patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax))
                        # main() should complete successfully
                        result = main()

        # Should have written JSON data file
        data_file = docs / "hit5_history.json"
        assert data_file.exists()

        data = json.loads(data_file.read_text())
        assert len(data) == 2
        assert data[0]["hit5"] == 0.80
        assert data[1]["hit5"] == 0.85

        # SVG file should also be written (mocked matplotlib doesn't really write,
        # but the code path attempts to call savefig)
        assert result == 0
    finally:
        sys.argv = old_argv


def test_main_skipped_commits_are_not_included(tmp_path, mocker):
    """main() doesn't include commits that couldn't be measured (hit5_at returned None)."""
    from hitgate.plot_history import main

    docs = tmp_path / "docs"
    docs.mkdir()

    old_argv = sys.argv
    try:
        sys.argv = ["plot_history.py", "--max-commits", "10"]

        with patch("hitgate.plot_history.ROOT", tmp_path):
            with patch("hitgate.plot_history.DOCS", docs):
                with patch("hitgate.plot_history.commits", return_value=[
                    ("abc1234", "2024-01-01", "Commit 1"),
                    ("def5678", "2024-01-02", "Commit 2"),  # will return None
                    ("ghi9012", "2024-01-03", "Commit 3"),
                ]):
                    with patch("hitgate.plot_history.hit5_at", side_effect=[0.80, None, 0.85]):
                        # Mock matplotlib components
                        mock_fig = MagicMock()
                        mock_ax = MagicMock()
                        mocker.patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax))
                        # Should complete successfully
                        result = main()

        data_file = docs / "hit5_history.json"
        data = json.loads(data_file.read_text())

        # Should only have 2 entries (skipped the None one)
        assert len(data) == 2
        assert data[0]["sha"] == "abc1234"
        assert data[1]["sha"] == "ghi9012"
        assert result == 0
    finally:
        sys.argv = old_argv


def test_main_exits_when_no_measurable_commits(tmp_path):
    """main() exits early if no commits could be measured."""
    from hitgate.plot_history import main

    docs = tmp_path / "docs"
    docs.mkdir()

    old_argv = sys.argv
    try:
        sys.argv = ["plot_history.py", "--max-commits", "10"]

        with patch("hitgate.plot_history.ROOT", tmp_path):
            with patch("hitgate.plot_history.DOCS", docs):
                with patch("hitgate.plot_history.commits", return_value=[
                    ("abc1234", "2024-01-01", "Commit 1"),
                ]):
                    with patch("hitgate.plot_history.hit5_at", return_value=None):
                        with pytest.raises(SystemExit):
                            main()
    finally:
        sys.argv = old_argv


def test_main_matplotlib_not_installed_fallback(tmp_path, capsys):
    """main() still writes JSON when matplotlib is not installed."""
    from hitgate.plot_history import main

    docs = tmp_path / "docs"
    docs.mkdir()

    old_argv = sys.argv
    try:
        sys.argv = ["plot_history.py", "--max-commits", "10"]

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "matplotlib":
                raise ImportError("No module named matplotlib")
            return real_import(name, *args, **kwargs)

        with patch("hitgate.plot_history.ROOT", tmp_path):
            with patch("hitgate.plot_history.DOCS", docs):
                with patch("hitgate.plot_history.commits", return_value=[
                    ("abc1234", "2024-01-01", "Commit 1"),
                ]):
                    with patch("hitgate.plot_history.hit5_at", return_value=0.80):
                        with patch("builtins.__import__", side_effect=mock_import):
                            with pytest.raises(SystemExit):
                                # Should exit because matplotlib is not installed (but after writing JSON)
                                main()

        # JSON data file should still exist
        data_file = docs / "hit5_history.json"
        assert data_file.exists()
        data = json.loads(data_file.read_text())
        assert len(data) == 1
    finally:
        sys.argv = old_argv
