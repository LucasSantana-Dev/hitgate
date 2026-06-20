"""Unit tests for ragcore.chunkers — the public interface is chunk_file(path, text) -> List[Chunk]
and the individual language chunkers. No index, no model, no disk writes."""
from __future__ import annotations

from pathlib import Path

import pytest

from ragcore.chunkers import (
    Chunk,
    chunk_fallback,
    chunk_file,
    chunk_python,
    chunk_shell,
    chunk_ts,
    detect_language,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _symbols(chunks: list[Chunk]) -> list[str]:
    return [c[3] for c in chunks]


def _texts(chunks: list[Chunk]) -> list[str]:
    return [c[2] for c in chunks]


def _assert_shape(chunks: list[Chunk]) -> None:
    for start, end, text, symbol in chunks:
        assert isinstance(start, int) and start >= 1
        assert isinstance(end, int) and end >= start
        assert isinstance(text, str) and text.strip()
        assert isinstance(symbol, str)


# ---------------------------------------------------------------------------
# chunk_python
# ---------------------------------------------------------------------------

_TWO_FUNCS = """\
def foo(x, y):
    \"\"\"Add two values and return the combined result.\"\"\"
    return x + y


def bar(items):
    \"\"\"Filter empty strings from a list of items.\"\"\"
    return [item for item in items if item]
"""

_FUNC_WITH_PREAMBLE = """\
# This module-level comment and constant are long enough to become a gap chunk in the index.
MODULE_CONSTANT = "a string value that is definitely longer than forty characters total"


def worker():
    return MODULE_CONSTANT
"""

_CONSTANTS_ONLY = """\
# No functions or classes — only top-level assignments.
DATABASE_URL = "sqlite:///app.db"
DEBUG = False
MAX_RETRIES = 3
TIMEOUT_SECONDS = 30
LOG_LEVEL = "INFO"
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
"""

_SYNTAX_ERROR = (
    "def broken(:\n"
    "    # This function body contains content that is long enough for chunk_fallback\n"
    "    # to produce at least one word-count window from the plain text.\n"
    "    pass\n"
)

_CLASS_AND_FUNC = """\
class Foo:
    \"\"\"A simple class with a method that returns a constant value.\"\"\"

    def method(self):
        return 42


def standalone():
    \"\"\"A standalone function that returns a simple computed string value.\"\"\"
    return "result"
"""


def test_chunk_python_one_chunk_per_top_level_symbol():
    chunks = chunk_python(_TWO_FUNCS)
    _assert_shape(chunks)
    syms = _symbols(chunks)
    assert "foo" in syms
    assert "bar" in syms


def test_chunk_python_class_and_function_both_captured():
    chunks = chunk_python(_CLASS_AND_FUNC)
    _assert_shape(chunks)
    syms = _symbols(chunks)
    assert "Foo" in syms
    assert "standalone" in syms


def test_chunk_python_gap_chunk_captures_module_level_preamble():
    chunks = chunk_python(_FUNC_WITH_PREAMBLE)
    _assert_shape(chunks)
    syms = _symbols(chunks)
    assert "worker" in syms
    # The module-level constant above the function must appear as a gap chunk
    assert "<module>" in syms, "module-level preamble should be captured as a gap chunk"


def test_chunk_python_constants_only_falls_back_to_word_windows():
    # A file with no def/class should use chunk_fallback and still produce chunks.
    chunks = chunk_python(_CONSTANTS_ONLY)
    _assert_shape(chunks)
    assert chunks, "constants-only file must not be silently dropped"


def test_chunk_python_syntax_error_falls_back_to_word_windows():
    chunks = chunk_python(_SYNTAX_ERROR)
    _assert_shape(chunks)
    assert chunks, "syntax error must fall back to chunk_fallback, not crash"


def test_chunk_python_no_empty_text():
    chunks = chunk_python(_TWO_FUNCS)
    assert all(c[2].strip() for c in chunks)


def test_chunk_python_line_numbers_are_one_indexed():
    chunks = chunk_python(_TWO_FUNCS)
    assert all(c[0] >= 1 for c in chunks)


# ---------------------------------------------------------------------------
# chunk_ts
# ---------------------------------------------------------------------------

_TS_EXPORT_FUNCTION = """\
export function greet(name: string): string {
  return `Hello ${name}`;
}
"""

_TS_ASYNC_FUNCTION = """\
async function fetchData(url: string): Promise<unknown> {
  const res = await fetch(url);
  return res.json();
}
"""

_TS_CLASS = """\
export class Retriever {
  search(query: string) {
    return [];
  }
}
"""


def test_chunk_ts_export_function_is_captured():
    chunks = chunk_ts(_TS_EXPORT_FUNCTION)
    _assert_shape(chunks)
    assert any("greet" in c[3] for c in chunks)


def test_chunk_ts_async_function_is_captured():
    chunks = chunk_ts(_TS_ASYNC_FUNCTION)
    _assert_shape(chunks)
    assert any("fetchData" in c[3] for c in chunks)


def test_chunk_ts_class_is_captured():
    chunks = chunk_ts(_TS_CLASS)
    _assert_shape(chunks)
    assert any("Retriever" in c[3] for c in chunks)


def test_chunk_ts_empty_file_falls_back():
    chunks = chunk_ts("")
    # fallback may produce empty list for truly empty input — that's fine
    assert isinstance(chunks, list)


# ---------------------------------------------------------------------------
# chunk_shell
# ---------------------------------------------------------------------------

_SHELL_TWO_FUNCS = """\
setup() {
  echo "setting up the test environment before each run"
  mkdir -p /tmp/test-workspace
}

teardown() {
  echo "tearing down the test environment after each run"
  rm -rf /tmp/test-workspace
}
"""

_SHELL_NESTED_BRACES = """\
run_with_retry() {
  for i in 1 2 3; do
    if cmd; then
      break
    fi
  done
}
"""


def test_chunk_shell_captures_function_block():
    chunks = chunk_shell(_SHELL_TWO_FUNCS)
    _assert_shape(chunks)
    syms = _symbols(chunks)
    assert "setup" in syms
    assert "teardown" in syms


def test_chunk_shell_nested_braces_do_not_prematurely_close():
    chunks = chunk_shell(_SHELL_NESTED_BRACES)
    _assert_shape(chunks)
    assert chunks
    # The entire function body (including the nested for/if braces) must be in one chunk
    assert "for i in" in chunks[0][2]


def test_chunk_shell_no_functions_falls_back():
    chunks = chunk_shell("echo hello\necho world\n")
    assert isinstance(chunks, list)


# ---------------------------------------------------------------------------
# chunk_fallback
# ---------------------------------------------------------------------------

_LONG_TEXT = "\n".join(f"Word{i} " * 10 for i in range(100))  # ~1000 words


def test_chunk_fallback_produces_at_least_one_chunk():
    chunks = chunk_fallback(_LONG_TEXT)
    _assert_shape(chunks)
    assert chunks


def test_chunk_fallback_empty_text_returns_empty_list():
    assert chunk_fallback("") == []


def test_chunk_fallback_short_text_below_min_chars_returns_empty():
    assert chunk_fallback("hi") == []


def test_chunk_fallback_long_text_produces_multiple_windows():
    chunks = chunk_fallback(_LONG_TEXT)
    assert len(chunks) > 1, "long text should produce multiple word-count windows"


def test_chunk_fallback_symbol_is_empty_string():
    chunks = chunk_fallback(_LONG_TEXT)
    assert all(c[3] == "" for c in chunks)


# ---------------------------------------------------------------------------
# detect_language
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("suffix,expected", [
    (".py", "python"),
    (".ts", "typescript"),
    (".tsx", "typescript"),
    (".js", "javascript"),
    (".jsx", "javascript"),
    (".sh", "shell"),
    (".bash", "shell"),
    (".md", "markdown"),
    (".yml", "yaml"),
    (".json", "json"),
    (".toml", "toml"),
    (".unknown", "text"),
])
def test_detect_language_by_extension(suffix, expected):
    assert detect_language(Path(f"file{suffix}")) == expected


# ---------------------------------------------------------------------------
# chunk_file dispatch
# ---------------------------------------------------------------------------

def test_chunk_file_dispatches_python_by_extension():
    chunks = chunk_file(Path("module.py"), _TWO_FUNCS)
    _assert_shape(chunks)
    assert any(c[3] in ("foo", "bar") for c in chunks)


def test_chunk_file_dispatches_ts_by_extension():
    chunks = chunk_file(Path("component.ts"), _TS_EXPORT_FUNCTION)
    _assert_shape(chunks)
    assert chunks


def test_chunk_file_dispatches_shell_by_extension():
    chunks = chunk_file(Path("script.sh"), _SHELL_TWO_FUNCS)
    _assert_shape(chunks)
    assert chunks


def test_chunk_file_dispatches_markdown_to_fallback():
    text = "# Title\n\nThis is a paragraph long enough to be included as a chunk in the index."
    chunks = chunk_file(Path("README.md"), text)
    _assert_shape(chunks)
    assert chunks


def test_chunk_file_dispatches_unknown_extension_to_fallback():
    text = "Some plain text content that is definitely longer than the minimum chunk character threshold."
    chunks = chunk_file(Path("data.xyz"), text)
    _assert_shape(chunks)
    assert chunks
