"""Tests for hitgate/audit_contamination.py — contamination detection in eval sets.

Tests verify: load_cases handles malformed/empty JSON, classify() returns
ok/scope-mismatch/CONTAMINATED, and main() exits 0/1 correctly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# load_cases — JSON parsing and validation
# ---------------------------------------------------------------------------


def test_load_cases_valid_jsonl(tmp_path):
    """load_cases parses a valid JSONL file."""
    from hitgate.audit_contamination import load_cases

    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps({"query": "q1", "expect_path_contains": "file.py", "expect_scope": "code"}) + "\n"
        + json.dumps({"query": "q2", "expect_path_contains": "readme.md", "expect_scope": "markdown"}) + "\n"
    )

    cases = load_cases(dataset)
    assert len(cases) == 2
    assert cases[0]["query"] == "q1"
    assert cases[1]["query"] == "q2"


def test_load_cases_skips_empty_lines(tmp_path):
    """load_cases skips blank lines gracefully."""
    from hitgate.audit_contamination import load_cases

    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps({"query": "q1", "expect_path_contains": "file.py", "expect_scope": "code"}) + "\n"
        + "\n"  # blank line
        + "   \n"  # whitespace-only line
        + json.dumps({"query": "q2", "expect_path_contains": "readme.md", "expect_scope": "markdown"}) + "\n"
    )

    cases = load_cases(dataset)
    assert len(cases) == 2


def test_load_cases_malformed_json_exits(tmp_path):
    """load_cases exits with a clear error on malformed JSON."""
    from hitgate.audit_contamination import load_cases

    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps({"query": "q1", "expect_path_contains": "file.py", "expect_scope": "code"}) + "\n"
        + "{ invalid json }\n"  # malformed
    )

    with pytest.raises(SystemExit) as exc_info:
        load_cases(dataset)
    assert exc_info.value.code != 0


def test_load_cases_empty_expect_path_exits(tmp_path):
    """load_cases rejects cases with empty expect_path_contains."""
    from hitgate.audit_contamination import load_cases

    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps({"query": "q1", "expect_path_contains": "", "expect_scope": "code"}) + "\n"
    )

    with pytest.raises(SystemExit) as exc_info:
        load_cases(dataset)
    assert exc_info.value.code != 0


def test_load_cases_missing_expect_key_skips_gracefully(tmp_path):
    """load_cases gracefully skips cases without expect_path_contains key."""
    from hitgate.audit_contamination import load_cases

    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps({"query": "q1", "expect_scope": "code"}) + "\n"
        + json.dumps({"query": "q2", "expect_path_contains": "target.py", "expect_scope": "code"}) + "\n"
    )

    # Should skip the first case (missing key) and include the second
    cases = load_cases(dataset)
    assert len(cases) == 1
    assert cases[0]["query"] == "q2"


def test_load_cases_list_expect_path(tmp_path):
    """load_cases handles expect_path_contains as a list."""
    from hitgate.audit_contamination import load_cases

    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps({
            "query": "q1",
            "expect_path_contains": ["file1.py", "file2.py"],
            "expect_scope": "code"
        }) + "\n"
    )

    cases = load_cases(dataset)
    assert len(cases) == 1
    assert cases[0]["expect_path_contains"] == ["file1.py", "file2.py"]


def test_load_cases_empty_list_expect_path_exits(tmp_path):
    """load_cases rejects cases where expect_path_contains is an empty list."""
    from hitgate.audit_contamination import load_cases

    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps({"query": "q1", "expect_path_contains": [], "expect_scope": "code"}) + "\n"
    )

    with pytest.raises(SystemExit) as exc_info:
        load_cases(dataset)
    assert exc_info.value.code != 0


def test_load_cases_nonexistent_file_exits(tmp_path):
    """load_cases exits clearly when dataset file doesn't exist."""
    from hitgate.audit_contamination import load_cases

    missing = tmp_path / "nonexistent.jsonl"

    with pytest.raises(SystemExit) as exc_info:
        load_cases(missing)
    assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# classify — verdict classification (ok / scope-mismatch / CONTAMINATED)
# ---------------------------------------------------------------------------


def test_classify_ok_path_in_corpus_any_scope(tmp_path):
    """classify returns 'ok' when expected path is in corpus."""
    from hitgate.audit_contamination import classify

    case = {
        "query": "q1",
        "expect_path_contains": "target.py",
        "expect_scope": "code",
    }
    corpus = [
        ("code", "src/target.py"),
        ("code", "src/other.py"),
    ]

    verdict = classify(case, corpus)
    assert verdict == "ok"


def test_classify_ok_ignores_scope_when_not_specified(tmp_path):
    """classify returns 'ok' when scope is not specified in case."""
    from hitgate.audit_contamination import classify

    case = {
        "query": "q1",
        "expect_path_contains": "target.py",
        # no expect_scope
    }
    corpus = [
        ("markdown", "docs/target.py"),
    ]

    verdict = classify(case, corpus)
    assert verdict == "ok"


def test_classify_scope_mismatch_path_exists_outside_scope(tmp_path):
    """classify returns 'scope-mismatch' when path is in corpus but outside declared scope."""
    from hitgate.audit_contamination import classify

    case = {
        "query": "q1",
        "expect_path_contains": "target.py",
        "expect_scope": "code",
    }
    corpus = [
        ("markdown", "docs/target.py"),  # in corpus but markdown, not code
    ]

    verdict = classify(case, corpus)
    assert verdict == "scope-mismatch"


def test_classify_contaminated_path_not_in_corpus(tmp_path):
    """classify returns 'CONTAMINATED' when expected path is not in corpus at all."""
    from hitgate.audit_contamination import classify

    case = {
        "query": "q1",
        "expect_path_contains": "target.py",
        "expect_scope": "code",
    }
    corpus = [
        ("code", "src/other.py"),
        ("code", "src/another.py"),
    ]

    verdict = classify(case, corpus)
    assert verdict == "CONTAMINATED"


def test_classify_ok_with_substring_match(tmp_path):
    """classify matches expect_path_contains as a substring."""
    from hitgate.audit_contamination import classify

    case = {
        "query": "q1",
        "expect_path_contains": "target",  # substring, not full path
        "expect_scope": "code",
    }
    corpus = [
        ("code", "src/config_target_handler.py"),
    ]

    verdict = classify(case, corpus)
    assert verdict == "ok"


def test_classify_multiple_scope_list(tmp_path):
    """classify handles scope as a list."""
    from hitgate.audit_contamination import classify

    case = {
        "query": "q1",
        "expect_path_contains": "target.py",
        "expect_scope": ["code", "markdown"],
    }
    corpus = [
        ("markdown", "docs/target.py"),
    ]

    verdict = classify(case, corpus)
    assert verdict == "ok"  # scope-mismatch would be if NOT in either code or markdown


# ---------------------------------------------------------------------------
# main() — CLI integration and exit codes
# ---------------------------------------------------------------------------


def test_main_exit_0_when_no_contamination(tmp_path, monkeypatch):
    """main() exits 0 when all cases are ok."""
    from hitgate.audit_contamination import main
    import sqlite3

    # Create a minimal index in a temp directory
    db = tmp_path / ".rag-index" / "index.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE chunks (id INTEGER PRIMARY KEY, source_type TEXT, path TEXT)"
    )
    conn.execute("INSERT INTO chunks VALUES (1, 'code', 'src/target.py')")
    conn.commit()
    conn.close()

    # Create eval dataset
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps({
            "query": "q1",
            "expect_path_contains": "target.py",
            "expect_scope": "code",
        }) + "\n"
    )

    # Mock DB path to our test index
    old_argv = sys.argv
    try:
        sys.argv = ["audit.py", "--dataset", str(dataset)]
        # Patch the DB constant
        from hitgate import audit_contamination
        original_db = audit_contamination.DB
        audit_contamination.DB = db
        try:
            code = main()
        finally:
            audit_contamination.DB = original_db
    finally:
        sys.argv = old_argv

    assert code == 0


def test_main_exit_1_when_contaminated(tmp_path, monkeypatch):
    """main() exits 1 when contaminated cases are found."""
    from hitgate.audit_contamination import main
    import sqlite3

    # Create a minimal index
    db = tmp_path / ".rag-index" / "index.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE chunks (id INTEGER PRIMARY KEY, source_type TEXT, path TEXT)"
    )
    conn.execute("INSERT INTO chunks VALUES (1, 'code', 'src/other.py')")
    conn.commit()
    conn.close()

    # Create eval dataset with a case that's not in the index
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps({
            "query": "q1",
            "expect_path_contains": "target.py",
            "expect_scope": "code",
        }) + "\n"
    )

    old_argv = sys.argv
    try:
        sys.argv = ["audit.py", "--dataset", str(dataset)]
        from hitgate import audit_contamination
        original_db = audit_contamination.DB
        audit_contamination.DB = db
        try:
            code = main()
        finally:
            audit_contamination.DB = original_db
    finally:
        sys.argv = old_argv

    assert code == 1


def test_main_reports_scope_mismatch(tmp_path, capsys):
    """main() reports scope-mismatch cases as warnings."""
    from hitgate.audit_contamination import main
    import sqlite3

    # Create a minimal index
    db = tmp_path / ".rag-index" / "index.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE chunks (id INTEGER PRIMARY KEY, source_type TEXT, path TEXT)"
    )
    conn.execute("INSERT INTO chunks VALUES (1, 'markdown', 'docs/target.py')")
    conn.commit()
    conn.close()

    # Create eval dataset expecting code scope but target is only in markdown
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps({
            "query": "my query about target",
            "expect_path_contains": "target.py",
            "expect_scope": "code",
        }) + "\n"
    )

    old_argv = sys.argv
    try:
        sys.argv = ["audit.py", "--dataset", str(dataset)]
        from hitgate import audit_contamination
        original_db = audit_contamination.DB
        audit_contamination.DB = db
        try:
            code = main()
        finally:
            audit_contamination.DB = original_db
    finally:
        sys.argv = old_argv

    captured = capsys.readouterr().out
    assert "scope-mismatch" in captured
    # Should still exit 0 (warning, not failure)
    assert code == 0


def test_main_respects_dataset_arg(tmp_path):
    """main() accepts custom dataset path via --dataset."""
    from hitgate.audit_contamination import main
    import sqlite3

    # Create a minimal index
    db = tmp_path / ".rag-index" / "index.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE chunks (id INTEGER PRIMARY KEY, source_type TEXT, path TEXT)"
    )
    conn.execute("INSERT INTO chunks VALUES (1, 'code', 'src/target.py')")
    conn.commit()
    conn.close()

    # Create eval dataset with custom path
    dataset = tmp_path / "my_eval_set.jsonl"
    dataset.write_text(
        json.dumps({
            "query": "q1",
            "expect_path_contains": "target.py",
            "expect_scope": "code",
        }) + "\n"
    )

    old_argv = sys.argv
    try:
        sys.argv = ["audit.py", "--dataset", str(dataset)]
        from hitgate import audit_contamination
        original_db = audit_contamination.DB
        audit_contamination.DB = db
        try:
            code = main()
        finally:
            audit_contamination.DB = original_db
    finally:
        sys.argv = old_argv

    assert code == 0
