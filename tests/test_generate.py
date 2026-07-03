"""Unit tests for eval.generate — public interface is generate() and the heuristic helpers.
No LLM calls, no disk writes, no index."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# RAG_SOURCE_ROOTS must be set before config.py is imported (it reads the env at module level).
# Default to the repo root so integration tests work without an explicit env var.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
os.environ.setdefault("RAG_SOURCE_ROOTS", _REPO_ROOT)

from hitgate.generate import (
    _extract_docstring,
    _extract_jsdoc_before,
    _first_comment,
    _heuristic,
    _infer_intent,
    _to_words,
)

# ---------------------------------------------------------------------------
# _to_words
# ---------------------------------------------------------------------------

def test_to_words_snake():
    assert _to_words("chunk_python") == "chunk python"


def test_to_words_camel():
    assert _to_words("getUserProfile") == "get user profile"


def test_to_words_mixed():
    assert _to_words("iter_code_sources") == "iter code sources"


# ---------------------------------------------------------------------------
# _extract_docstring
# ---------------------------------------------------------------------------

_WITH_DOCSTRING = '''\
def chunk_python(text: str):
    """Splits source files into smaller fragments at logical declaration boundaries."""
    pass
'''

_WITH_MULTILINE_DOCSTRING = '''\
def build():
    """Chunk and embed configured source roots into a local sqlite index.

    For each root in RAG_SOURCE_ROOTS this indexes source code and docs.
    """
    pass
'''

_NO_DOCSTRING = '''\
def helper():
    x = 1
    return x
'''

_MODULE_DOCSTRING = '''\
"""Configuration for the retriever — env-var driven, zero external deps."""

import os
'''


def test_extract_docstring_single_line():
    result = _extract_docstring(_WITH_DOCSTRING)
    assert result is not None
    assert "Splits source files" in result


def test_extract_docstring_multiline_first_line():
    result = _extract_docstring(_WITH_MULTILINE_DOCSTRING)
    assert result is not None
    assert "Chunk and embed" in result


def test_extract_docstring_none_when_absent():
    assert _extract_docstring(_NO_DOCSTRING) is None


def test_extract_docstring_module_level():
    result = _extract_docstring(_MODULE_DOCSTRING)
    assert result is not None
    assert "Configuration" in result


def test_extract_docstring_too_short_returns_none():
    code = 'def f():\n    """Short."""\n    pass\n'
    assert _extract_docstring(code) is None


_WITH_JSDOC_INLINE = '/** Rejection produced when a withTimeout deadline fires first. */\nexport class TimeoutError {}'
_WITH_JSDOC_MULTILINE = (
    '/**\n'
    ' * Race promise against a deadline and reject with TimeoutError if it fires.\n'
    ' * @param promise the operation to bound\n'
    ' */\n'
    'export const withTimeout = () => {}'
)


def test_extract_docstring_single_line_jsdoc():
    result = _extract_docstring(_WITH_JSDOC_INLINE)
    assert result is not None
    assert "Rejection produced" in result


def test_extract_docstring_multiline_jsdoc():
    result = _extract_docstring(_WITH_JSDOC_MULTILINE)
    assert result is not None
    assert "Race promise" in result


def test_extract_docstring_jsdoc_skips_at_tags():
    code = '/** @param x the value */\nexport function f(x) {}'
    assert _extract_docstring(code) is None


# ---------------------------------------------------------------------------
# _extract_jsdoc_before
# ---------------------------------------------------------------------------

_JSDOC_MULTILINE_LINES = [
    "/**",
    " * Race promise against a deadline — rejects with TimeoutError if fires.",
    " * @param promise the operation",
    " */",
    "export const withTimeout = () => {}",
]

_JSDOC_INLINE_LINES = [
    "/** Rejection produced when a withTimeout deadline fires first. */",
    "export class TimeoutError {}",
]

_SLASH_COMMENT_LINES = [
    "// Builds a presigned URL for the given S3 key, expiring after ttlSeconds.",
    "export function buildPresignedUrl(key: string): string {",
]

_NO_COMMENT_LINES = [
    "export function noComment(): void {",
]


def test_jsdoc_before_multiline():
    result = _extract_jsdoc_before(_JSDOC_MULTILINE_LINES, start_line=5)
    assert result is not None
    assert "Race promise" in result


def test_jsdoc_before_inline():
    result = _extract_jsdoc_before(_JSDOC_INLINE_LINES, start_line=2)
    assert result is not None
    assert "Rejection produced" in result


def test_jsdoc_before_skips_at_tags():
    lines = ["/** @param x the value */", "export function f(x: number) {}"]
    result = _extract_jsdoc_before(lines, start_line=2)
    assert result is None


def test_jsdoc_before_slash_comment():
    result = _extract_jsdoc_before(_SLASH_COMMENT_LINES, start_line=2)
    assert result is not None
    assert "presigned URL" in result


def test_jsdoc_before_no_comment():
    result = _extract_jsdoc_before(_NO_COMMENT_LINES, start_line=1)
    assert result is None


def test_jsdoc_before_start_line_one():
    result = _extract_jsdoc_before(_JSDOC_INLINE_LINES, start_line=1)
    assert result is None


# ---------------------------------------------------------------------------
# _first_comment
# ---------------------------------------------------------------------------

_WITH_COMMENT = '''\
def is_excluded_path(path):
    # Skip directories that should never appear in the index
    for part in path.parts:
        if part in EXCLUDED:
            return True
'''

_NO_COMMENT = 'def simple():\n    return 42\n'

_SHORT_COMMENT = 'def f():\n    # skip\n    pass\n'


def test_first_comment_found():
    result = _first_comment(_WITH_COMMENT)
    assert result is not None
    assert "Skip directories" in result


def test_first_comment_none_when_absent():
    assert _first_comment(_NO_COMMENT) is None


def test_first_comment_too_short_skipped():
    assert _first_comment(_SHORT_COMMENT) is None


# ---------------------------------------------------------------------------
# _heuristic
# ---------------------------------------------------------------------------

def test_heuristic_high_confidence_from_docstring():
    text = _WITH_DOCSTRING
    query, conf = _heuristic("chunk_python", text, "chunkers.py")
    assert conf == "high"
    assert "Splits source files" in query


def test_heuristic_medium_confidence_from_symbol():
    query, conf = _heuristic("iter_code_sources", _NO_DOCSTRING, "build.py")
    assert conf == "medium"
    assert "iter code sources" in query


def test_heuristic_medium_with_comment():
    query, conf = _heuristic("is_excluded_path", _WITH_COMMENT, "build.py")
    assert conf in ("high", "medium")


def test_heuristic_empty_query_on_trivial_module_chunk():
    trivial = "import os\nimport re\n"
    query, conf = _heuristic("<module>", trivial, "build.py")
    # Either empty (caller drops it) or low confidence
    assert conf == "low" or query == ""


def test_heuristic_module_chunk_with_comment():
    text = "# Skip directories like node_modules and venv from the index walk\nEXCLUDED = {'node_modules'}"
    query, conf = _heuristic("<module>", text, "config.py")
    assert conf == "low"
    assert "Skip directories" in query


# ---------------------------------------------------------------------------
# _infer_intent
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename,expected", [
    ("retrieval.py", "retrieval"),
    ("query.py", "retrieval"),
    ("build.py", "indexing"),
    ("chunkers.py", "indexing"),
    ("config.py", "infrastructure"),
    ("mcp_server.py", "infrastructure"),
    ("run.py", "infrastructure"),
])
def test_infer_intent(filename, expected):
    assert _infer_intent(Path(filename)) == expected


# ---------------------------------------------------------------------------
# generate() integration — no LLM, no external calls, uses repo source roots
# ---------------------------------------------------------------------------

_ROOTS = [Path(_REPO_ROOT)]  # pass explicitly so tests don't depend on SOURCE_ROOTS env resolution


def test_generate_produces_valid_cases():
    from hitgate.generate import generate

    cases = generate(min_confidence="high", limit=10, roots=_ROOTS)
    assert len(cases) > 0
    for case in cases:
        assert "query" in case
        assert "expect_path_contains" in case
        assert "expect_scope" in case
        assert case["expect_scope"] == "code"
        assert case["query"].strip() != ""


def test_generate_existing_skips_covered_files(tmp_path):
    from hitgate.generate import generate

    # Write a fake existing golden set covering "retrieval.py"
    existing = tmp_path / "existing.jsonl"
    existing.write_text(
        json.dumps({"query": "x", "expect_path_contains": "retrieval.py", "expect_scope": "code"}) + "\n"
    )

    cases = generate(existing_path=existing, min_confidence="medium", limit=0, roots=_ROOTS)
    assert len(cases) > 0, "should generate cases for uncovered files"
    covered = {c["expect_path_contains"] for c in cases}
    assert "retrieval.py" not in covered


def test_generate_respects_limit():
    from hitgate.generate import generate

    cases = generate(min_confidence="medium", limit=5, roots=_ROOTS)
    assert len(cases) <= 5


def test_generate_harness_format_only():
    """Default output (no --full) must contain only harness-recognised fields."""
    from hitgate.generate import _harness_fields, generate

    cases = generate(min_confidence="high", limit=5, roots=_ROOTS)
    _HARNESS = {"query", "expect_path_contains", "expect_scope", "intent", "paraphrase"}
    for case in cases:
        cleaned = _harness_fields(case)
        assert set(cleaned.keys()).issubset(_HARNESS)
        assert "_confidence" not in cleaned
        assert "_symbol" not in cleaned


# ---------------------------------------------------------------------------
# _llm_queries — mocked urllib.request.urlopen, no real API calls
# ---------------------------------------------------------------------------

from hitgate.generate import _llm_queries  # noqa: E402


def _make_urlopen_mock(content: str):
    """Return a patch-ready mock for urllib.request.urlopen that yields `content`."""
    resp = MagicMock()
    resp.read.return_value = json.dumps({
        "choices": [{"message": {"content": content}}]
    }).encode()
    mock = MagicMock()
    mock.return_value.__enter__.return_value = resp
    mock.return_value.__exit__.return_value = False
    return mock


_LLM_KWARGS = dict(
    chunk_text="def build(): ...",
    filename="build.py",
    symbol="build",
    model="gpt-4o-mini",
    base_url="https://api.openai.com/v1",
    api_key="sk-test",
)


def test_llm_queries_success():
    payload = json.dumps({"identifier": "how does the build function work", "paraphrase": "where is the index built from source roots"})
    with patch("urllib.request.urlopen", _make_urlopen_mock(payload)):
        result = _llm_queries(**_LLM_KWARGS)
    assert result is not None
    assert result["identifier"] == "how does the build function work"
    assert result["paraphrase"] == "where is the index built from source roots"


def test_llm_queries_malformed_json():
    with patch("urllib.request.urlopen", _make_urlopen_mock("not valid json at all")):
        result = _llm_queries(**_LLM_KWARGS)
    assert result is None


def test_llm_queries_missing_keys():
    payload = json.dumps({"something_else": "value"})
    with patch("urllib.request.urlopen", _make_urlopen_mock(payload)):
        result = _llm_queries(**_LLM_KWARGS)
    assert result is None


def test_llm_queries_http_error():
    import urllib.error
    mock = MagicMock(side_effect=urllib.error.URLError("connection refused"))
    with patch("urllib.request.urlopen", mock):
        result = _llm_queries(**_LLM_KWARGS)
    assert result is None


def test_llm_queries_fenced_json_response():
    """LLM often wraps JSON in ```json fences — the parser must strip them."""
    raw = '```json\n{"identifier": "build index from source", "paraphrase": "where are documents indexed"}\n```'
    with patch("urllib.request.urlopen", _make_urlopen_mock(raw)):
        result = _llm_queries(**_LLM_KWARGS)
    assert result is not None
    assert "identifier" in result and "paraphrase" in result


def test_llm_queries_logs_exception_to_stderr(capsys):
    """LLM query failures should log a WARN to stderr and return None (not silent)."""
    import urllib.error
    mock = MagicMock(side_effect=urllib.error.URLError("connection refused"))
    with patch("urllib.request.urlopen", mock):
        result = _llm_queries(**_LLM_KWARGS)
    assert result is None
    captured = capsys.readouterr()
    assert "WARN: LLM query failed" in captured.err
    assert "connection refused" in captured.err


# ---------------------------------------------------------------------------
# generate(llm=True) — integration path; two cases per chunk, _source=llm
# ---------------------------------------------------------------------------


def test_generate_llm_path_emits_two_cases_per_chunk(tmp_path):
    """With a mocked LLM, generate(llm=True) should emit identifier + paraphrase."""
    # Write a tiny Python file with a docstring so min_confidence=high is met
    src = tmp_path / "mymodule.py"
    src.write_text(
        'def do_something():\n    """Performs the core transformation step for the pipeline."""\n    pass\n'
    )

    payload = json.dumps({
        "identifier": "do something function in mymodule",
        "paraphrase": "where is the main transformation logic implemented",
    })

    with patch("urllib.request.urlopen", _make_urlopen_mock(payload)):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            from hitgate.generate import generate
            cases = generate(llm=True, min_confidence="high", limit=0, roots=[tmp_path])

    assert len(cases) == 2
    sources = {c["_source"] for c in cases}
    assert sources == {"llm"}
    query_types = {c["_query_type"] for c in cases}
    assert query_types == {"identifier", "paraphrase"}
    paraphrase_cases = [c for c in cases if c.get("paraphrase") is True]
    assert len(paraphrase_cases) == 1


# ---------------------------------------------------------------------------
# Complex LLM mode branches — partial responses, timeout, LLM failure fallback
# ---------------------------------------------------------------------------


def test_generate_llm_only_identifier_no_paraphrase(tmp_path):
    """LLM response with only 'identifier' key emits 1 case (not 2)."""
    src = tmp_path / "mymodule.py"
    src.write_text(
        'def do_something():\n    """Performs the core transformation step for the pipeline."""\n    pass\n'
    )

    # LLM returns only identifier, no paraphrase
    payload = json.dumps({
        "identifier": "do something function in mymodule",
    })

    with patch("urllib.request.urlopen", _make_urlopen_mock(payload)):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            from hitgate.generate import generate
            cases = generate(llm=True, min_confidence="high", limit=0, roots=[tmp_path])

    # Should emit 1 case (the identifier)
    assert len(cases) == 1
    assert cases[0]["_query_type"] == "identifier"


def test_generate_llm_only_paraphrase_no_identifier(tmp_path):
    """LLM response with only 'paraphrase' key falls back to heuristic (since LLM didn't fully respond)."""
    src = tmp_path / "mymodule.py"
    src.write_text(
        'def do_something():\n    """Performs the core transformation step for the pipeline."""\n    pass\n'
    )

    # LLM returns only paraphrase, no identifier (incomplete response)
    payload = json.dumps({
        "paraphrase": "where is the main transformation logic implemented",
    })

    with patch("urllib.request.urlopen", _make_urlopen_mock(payload)):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            from hitgate.generate import generate
            cases = generate(llm=True, min_confidence="high", limit=0, roots=[tmp_path])

    # LLM response was incomplete (missing identifier), so it falls back to heuristic
    # The heuristic will use the docstring (high confidence)
    assert len(cases) >= 1
    # First case should be from heuristic fallback
    assert cases[0]["_source"] == "heuristic"
    assert "Performs the core transformation" in cases[0]["query"]


def test_generate_llm_failure_falls_back_to_heuristic(tmp_path):
    """When LLM fails, falls back to heuristic-generated query."""
    src = tmp_path / "mymodule.py"
    src.write_text(
        'def do_something():\n    """Performs the core transformation step for the pipeline."""\n    pass\n'
    )

    # LLM request fails (URLError)
    import urllib.error
    mock = MagicMock(side_effect=urllib.error.URLError("timeout"))

    with patch("urllib.request.urlopen", mock):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            from hitgate.generate import generate
            cases = generate(llm=True, min_confidence="high", limit=0, roots=[tmp_path])

    # Should fall back to heuristic
    assert len(cases) >= 1
    # First case from heuristic fallback
    assert cases[0]["_source"] == "heuristic"
    assert "Performs the core transformation" in cases[0]["query"]


def test_generate_multi_intent_merge():
    """generate() merges cases from different intent classes."""
    from hitgate.generate import generate

    # Use limit=0 (unlimited) to ensure we capture all intents across the repo.
    # limit=10 was too tight and sometimes yielded a single intent on CI (non-deterministic).
    cases = generate(min_confidence="medium", limit=0, roots=[Path(_REPO_ROOT)])

    # Should have cases with multiple intents
    intents = {c.get("intent") for c in cases}
    assert len(intents) > 1
    assert "indexing" in intents or "retrieval" in intents or "infrastructure" in intents


def test_generate_limit_cap(tmp_path):
    """generate(limit=N) caps output at N cases."""
    # Create multiple source files to exceed limit
    for i in range(5):
        src = tmp_path / f"module_{i}.py"
        src.write_text(
            f'def func_{i}():\n    """Function number {i} does something important in the system."""\n    pass\n'
        )

    from hitgate.generate import generate
    cases = generate(min_confidence="medium", limit=3, roots=[tmp_path])

    assert len(cases) <= 3


def test_generate_respects_existing_coverage(tmp_path):
    """generate() skips files already in the existing golden set."""
    from hitgate.generate import generate

    # Create source file
    src = tmp_path / "covered.py"
    src.write_text(
        'def important_func():\n    """A function that should be tested in retrieval eval."""\n    pass\n'
    )

    # Write an existing golden set covering covered.py
    existing = tmp_path / "existing.jsonl"
    existing.write_text(
        json.dumps({
            "query": "existing test for covered.py",
            "expect_path_contains": "covered.py",
            "expect_scope": "code",
        }) + "\n"
    )

    cases = generate(existing_path=existing, min_confidence="medium", limit=0, roots=[tmp_path])

    # Should skip covered.py
    for case in cases:
        assert "covered.py" not in case["expect_path_contains"]


# ---------------------------------------------------------------------------
# Edge cases in docstring and comment extraction
# ---------------------------------------------------------------------------


def test_heuristic_with_very_long_symbol(tmp_path):
    """_heuristic handles extremely long symbol names gracefully."""
    from hitgate.generate import _heuristic

    symbol = "a" * 500  # very long
    result, conf = _heuristic(symbol, "# some code", "test.py")
    assert isinstance(result, str)
    assert conf in ("high", "medium", "low")


def test_extract_docstring_with_unicode():
    """_extract_docstring handles unicode in docstrings."""
    from hitgate.generate import _extract_docstring

    code = '''def unicode_func():
    """Handles UTF-8: café, naïve, 日本語 — really quite cool."""
    pass
'''
    result = _extract_docstring(code)
    assert result is not None
    assert "café" in result or "UTF" in result


def test_extract_docstring_with_special_chars():
    """_extract_docstring handles special characters in docstrings."""
    from hitgate.generate import _extract_docstring

    code = r'''def special():
    """Regex pattern ^[a-z]+$ matches lowercase strings only."""
    pass
'''
    result = _extract_docstring(code)
    assert result is not None
    assert "Regex" in result or "pattern" in result


# ---------------------------------------------------------------------------
# Negative test cases: missing index, missing golden-case keys
# ---------------------------------------------------------------------------


def test_generate_with_empty_roots_returns_empty_list():
    """When generate() is called with empty roots, return empty candidates list."""
    from hitgate.generate import generate

    cases = generate(min_confidence="medium", limit=0, roots=[])
    assert cases == [], "Expected empty list when roots is empty"


def test_generate_with_nonexistent_roots_returns_empty_list():
    """When all provided roots don't exist, return empty candidates list."""
    from hitgate.generate import generate

    nonexistent = Path("/this/path/does/not/exist/anywhere")
    cases = generate(min_confidence="medium", limit=0, roots=[nonexistent])
    assert cases == [], "Expected empty list when all roots are nonexistent"


def test_generate_existing_golden_missing_expect_path_contains_key(tmp_path):
    """When a golden-case JSON line is valid but missing expect_path_contains key,
    it should be handled gracefully without raising an exception.
    The file should NOT be marked as covered (since we use .get() with default "").
    """
    from hitgate.generate import generate

    # Create a source file to generate from
    src = tmp_path / "test_module.py"
    src.write_text(
        'def important_func():\n    """A function that should be generated as a candidate."""\n    pass\n'
    )

    # Write an existing golden set with a line missing the expect_path_contains key
    # This is structurally valid JSON but missing a required key
    existing = tmp_path / "existing.jsonl"
    existing.write_text(
        json.dumps({"query": "test query", "expect_scope": "code"}) + "\n"  # missing expect_path_contains
    )

    # This should NOT raise an exception; the missing key is handled gracefully
    cases = generate(existing_path=existing, min_confidence="medium", limit=0, roots=[tmp_path])

    # The source file test_module.py should NOT be marked as covered, so we should get cases for it
    assert len(cases) > 0, "Expected cases to be generated since malformed golden case wasn't properly marked as covered"
    covered_files = {c["expect_path_contains"] for c in cases}
    assert "test_module.py" in covered_files, "test_module.py should be in generated cases since the golden case was missing the key"


def test_generate_existing_golden_with_multiple_missing_keys(tmp_path):
    """When multiple golden-case JSON lines are missing keys, all are handled gracefully."""
    from hitgate.generate import generate

    # Create source files
    for i in range(3):
        src = tmp_path / f"module_{i}.py"
        src.write_text(
            f'def func_{i}():\n    """Module {i} function that should generate candidates."""\n    pass\n'
        )

    # Write an existing golden set with several malformed lines
    existing = tmp_path / "existing.jsonl"
    with existing.open("w") as f:
        # Line 1: missing expect_path_contains
        f.write(json.dumps({"query": "q1", "expect_scope": "code"}) + "\n")
        # Line 2: missing both expect_path_contains and expect_scope
        f.write(json.dumps({"query": "q2"}) + "\n")
        # Line 3: well-formed (should mark file as covered)
        f.write(json.dumps({"query": "q3", "expect_path_contains": "module_1.py", "expect_scope": "code"}) + "\n")

    # This should NOT raise an exception
    cases = generate(existing_path=existing, min_confidence="medium", limit=0, roots=[tmp_path])

    # module_1.py should be covered (well-formed entry), but module_0.py and module_2.py should not be
    covered_files = {c["expect_path_contains"] for c in cases}
    assert "module_1.py" not in covered_files, "module_1.py should be covered by well-formed golden case"
    assert "module_0.py" in covered_files or "module_2.py" in covered_files, "At least one uncovered file should generate candidates"
