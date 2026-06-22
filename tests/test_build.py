"""Unit tests for ragcore.build — pure functions, path classification, exclusion logic, and batching."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from ragcore.build import (
    classify_repo,
    classify_type,
    is_excluded_path,
    _flush,
)


class TestIsExcludedPath:
    """Test path exclusion logic against EXCLUDED_DIR_PARTS."""

    def test_excludes_venv(self):
        assert is_excluded_path(Path("my_project/.venv/lib/python"))

    def test_excludes_node_modules(self):
        assert is_excluded_path(Path("frontend/node_modules/react"))

    def test_excludes_git(self):
        assert is_excluded_path(Path(".git/objects/ab"))

    def test_excludes_tests(self):
        assert is_excluded_path(Path("src/tests/unit"))

    def test_excludes_worktrees(self):
        assert is_excluded_path(Path(".worktrees/branch-123"))

    def test_excludes_wt_prefix(self):
        # .wt- prefix is a special case for worktree markers
        assert is_excluded_path(Path(".wt-branch-123/file.py"))

    def test_excludes_build_and_dist(self):
        assert is_excluded_path(Path("build/lib"))
        assert is_excluded_path(Path("dist/wheel"))

    def test_allows_normal_paths(self):
        assert not is_excluded_path(Path("src/main.py"))
        assert not is_excluded_path(Path("docs/api.md"))
        assert not is_excluded_path(Path("ragcore/build.py"))

    def test_allows_nested_normal_paths(self):
        assert not is_excluded_path(Path("src/module/submodule/file.py"))

    def test_excludes_deeply_nested_excluded(self):
        assert is_excluded_path(Path("src/module/__pycache__/main.pyc"))


class TestClassifyRepo:
    """Test repo classification from absolute paths."""

    def test_classifies_direct_match(self, tmp_path):
        root = tmp_path / "myrepo"
        root.mkdir()
        test_file = root / "file.py"

        with mock.patch("ragcore.build.SOURCE_ROOTS", [root]):
            result = classify_repo(test_file)
            assert result == "myrepo"

    def test_classifies_nested_file(self, tmp_path):
        root = tmp_path / "myrepo"
        (root / "src" / "module").mkdir(parents=True)
        test_file = root / "src" / "module" / "file.py"

        with mock.patch("ragcore.build.SOURCE_ROOTS", [root]):
            result = classify_repo(test_file)
            assert result == "myrepo"

    def test_returns_none_for_unrelated_path(self, tmp_path):
        root = tmp_path / "repoA"
        root.mkdir()
        other = tmp_path / "repoB" / "file.py"

        with mock.patch("ragcore.build.SOURCE_ROOTS", [root]):
            result = classify_repo(other)
            assert result is None

    def test_classifies_first_matching_root(self, tmp_path):
        rootA = tmp_path / "repoA"
        rootB = tmp_path / "repoB"
        rootA.mkdir()
        rootB.mkdir()
        test_file = rootB / "file.py"

        with mock.patch("ragcore.build.SOURCE_ROOTS", [rootA, rootB]):
            result = classify_repo(test_file)
            assert result == "repoB"

    def test_handles_symlinks(self, tmp_path):
        root = tmp_path / "realrepo"
        root.mkdir()
        link = tmp_path / "linkrepo"
        try:
            link.symlink_to(root)
        except OSError:
            pytest.skip("symlinks not supported on this platform")

        test_file = link / "file.py"

        with mock.patch("ragcore.build.SOURCE_ROOTS", [root]):
            result = classify_repo(test_file)
            # Should match via resolve()
            assert result in ("realrepo", "linkrepo")


class TestClassifyType:
    """Test source_type classification based on filename and path."""

    def test_readme_variations(self):
        assert classify_type(Path("README.md")) == "repo-readme"
        assert classify_type(Path("readme.md")) == "repo-readme"
        assert classify_type(Path("README.txt")) == "repo-readme"

    def test_changelog(self):
        assert classify_type(Path("CHANGELOG.md")) == "changelog"
        assert classify_type(Path("changelog.md")) == "changelog"

    def test_roadmap(self):
        assert classify_type(Path("docs/roadmap.md")) == "roadmap"

    def test_spec_in_docs_specs(self):
        # classify_type checks str(path) for "/docs/specs/", so need absolute-like paths
        assert classify_type(Path("/repo/docs/specs/api.md")) == "spec"
        assert classify_type(Path("/repo/docs/specs/design/component.md")) == "spec"

    def test_repo_docs_in_docs_dir(self):
        assert classify_type(Path("docs/api.md")) == "repo-docs"
        assert classify_type(Path("docs/guides/setup.md")) == "repo-docs"

    def test_markdown_at_root(self):
        assert classify_type(Path("CONTRIBUTING.md")) == "repo-docs"
        assert classify_type(Path("FAQ.md")) == "repo-docs"

    def test_code_extensions(self):
        assert classify_type(Path("main.py")) == "code"
        assert classify_type(Path("app.ts")) == "code"
        assert classify_type(Path("index.tsx")) == "code"
        assert classify_type(Path("index.js")) == "code"
        assert classify_type(Path("script.sh")) == "code"

    def test_other_files(self):
        assert classify_type(Path("LICENSE")) == "other"
        assert classify_type(Path("setup.json")) == "other"
        assert classify_type(Path("data.csv")) == "other"

    def test_case_insensitive_extensions(self):
        assert classify_type(Path("FILE.PY")) == "code"
        assert classify_type(Path("Readme.MD")) == "repo-readme"


class TestFlush:
    """Test _flush batching: embeddings are inserted correctly."""

    def test_flush_writes_rows_to_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                """CREATE TABLE chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    repo TEXT,
                    language TEXT,
                    symbol TEXT,
                    path TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    file_sha TEXT NOT NULL,
                    mtime REAL NOT NULL,
                    embedding BLOB NOT NULL
                )"""
            )

            # Mock model.encode to return dummy embeddings
            mock_model = mock.Mock()
            import numpy as np
            mock_model.encode.return_value = np.random.randn(2, 384).astype(np.float32)

            texts = ["hello world", "foo bar"]
            meta = [
                {
                    "source_type": "code",
                    "repo": "test-repo",
                    "language": "python",
                    "symbol": "func1",
                    "path": "/path/to/file.py",
                    "start": 1,
                    "end": 10,
                    "text": "hello world",
                    "sha": "abc123",
                    "mtime": 1234567890.0,
                },
                {
                    "source_type": "code",
                    "repo": "test-repo",
                    "language": "python",
                    "symbol": "func2",
                    "path": "/path/to/file.py",
                    "start": 11,
                    "end": 20,
                    "text": "foo bar",
                    "sha": "abc123",
                    "mtime": 1234567890.0,
                },
            ]

            # Call _flush with mocked model
            _flush(conn, mock_model, texts, meta)

            # Verify rows were inserted
            cur = conn.execute("SELECT COUNT(*) FROM chunks")
            count = cur.fetchone()[0]
            assert count == 2

            # Verify specific row
            cur = conn.execute("SELECT source_type, symbol, path FROM chunks WHERE symbol = ?", ("func1",))
            row = cur.fetchone()
            assert row == ("code", "func1", "/path/to/file.py")

            conn.close()

    def test_flush_respects_batch_size(self):
        """Flush should handle any batch size."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                """CREATE TABLE chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    repo TEXT,
                    language TEXT,
                    symbol TEXT,
                    path TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    file_sha TEXT NOT NULL,
                    mtime REAL NOT NULL,
                    embedding BLOB NOT NULL
                )"""
            )

            mock_model = mock.Mock()
            import numpy as np
            # Create 5 different embeddings
            embeddings = np.random.randn(5, 384).astype(np.float32)
            mock_model.encode.return_value = embeddings

            texts = [f"text{i}" for i in range(5)]
            meta = [
                {
                    "source_type": "code",
                    "repo": "repo",
                    "language": "python",
                    "symbol": f"sym{i}",
                    "path": f"/path/file{i}.py",
                    "start": i,
                    "end": i + 1,
                    "text": texts[i],
                    "sha": "sha",
                    "mtime": 0.0,
                }
                for i in range(5)
            ]

            _flush(conn, mock_model, texts, meta)

            cur = conn.execute("SELECT COUNT(*) FROM chunks")
            count = cur.fetchone()[0]
            assert count == 5

            conn.close()

    def test_flush_encodes_embedding_correctly(self):
        """Embedding blob should be serialized and deserialized correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                """CREATE TABLE chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    repo TEXT,
                    language TEXT,
                    symbol TEXT,
                    path TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    file_sha TEXT NOT NULL,
                    mtime REAL NOT NULL,
                    embedding BLOB NOT NULL
                )"""
            )

            mock_model = mock.Mock()
            import numpy as np
            # Create a known embedding
            test_embedding = np.array([[0.1, 0.2, 0.3, 0.4]], dtype=np.float32)
            mock_model.encode.return_value = test_embedding

            texts = ["test"]
            meta = [
                {
                    "source_type": "code",
                    "repo": "repo",
                    "language": "python",
                    "symbol": "sym",
                    "path": "/path/file.py",
                    "start": 1,
                    "end": 2,
                    "text": "test",
                    "sha": "sha",
                    "mtime": 0.0,
                }
            ]

            _flush(conn, mock_model, texts, meta)

            # Read embedding back
            cur = conn.execute("SELECT embedding FROM chunks LIMIT 1")
            blob = cur.fetchone()[0]
            restored = np.frombuffer(blob, dtype=np.float32)
            np.testing.assert_array_almost_equal(restored, test_embedding[0])

            conn.close()
