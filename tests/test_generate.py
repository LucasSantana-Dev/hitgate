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

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ragcore"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from generate import (
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
    from generate import generate

    cases = generate(min_confidence="high", limit=10, roots=_ROOTS)
    assert len(cases) > 0
    for case in cases:
        assert "query" in case
        assert "expect_path_contains" in case
        assert "expect_scope" in case
        assert case["expect_scope"] == "code"
        assert case["query"].strip() != ""


def test_generate_existing_skips_covered_files(tmp_path):
    from generate import generate

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
    from generate import generate

    cases = generate(min_confidence="medium", limit=5, roots=_ROOTS)
    assert len(cases) <= 5


def test_generate_harness_format_only():
    """Default output (no --full) must contain only harness-recognised fields."""
    from generate import _harness_fields, generate

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

from generate import _llm_queries  # noqa: E402


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
            from generate import generate
            cases = generate(llm=True, min_confidence="high", limit=0, roots=[tmp_path])

    assert len(cases) == 2
    sources = {c["_source"] for c in cases}
    assert sources == {"llm"}
    query_types = {c["_query_type"] for c in cases}
    assert query_types == {"identifier", "paraphrase"}
    paraphrase_cases = [c for c in cases if c.get("paraphrase") is True]
    assert len(paraphrase_cases) == 1
