"""Language-aware chunkers. Each returns list[(start_line, end_line, text, symbol_name)].

Keep chunks:
- Python: one chunk per top-level def/class (via stdlib ast).
- TS/JS: regex on top-level `export? (async )?(function|class|const NAME =)` blocks, brace-matched.
- Shell: regex on `NAME() {` blocks through closing `^}`.
- Config / others: fall back to markdown-style word-count windows.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List, Tuple

Chunk = Tuple[int, int, str, str]  # start_line (1-idx), end_line, text, symbol

MAX_CHUNK_LINES = 250
MIN_CHUNK_CHARS = 40


def chunk_python(text: str) -> List[Chunk]:
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return chunk_fallback(text)
    chunks: List[Chunk] = []
    symbol_ranges: List[Tuple[int, int]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = getattr(node, "lineno", 1)
            end = getattr(node, "end_lineno", start)
            body = "\n".join(lines[start - 1 : end])
            if len(body) >= MIN_CHUNK_CHARS:
                chunks.append((start, end, body[:8000], node.name))
                symbol_ranges.append((start, end))
    # Capture module-level regions between symbols: docstring, constants, imports.
    # Without this, files like config.py (mostly top-level assignments) would only
    # contribute their single helper function and lose all their constant definitions.
    if symbol_ranges:
        boundaries = [0] + [e for _, e in sorted(symbol_ranges)] + [len(lines)]
        starts = [0] + [s for s, _ in sorted(symbol_ranges)]
        gaps = [(boundaries[i] + 1, starts[i + 1] - 1) for i in range(len(starts) - 1)]
        gaps.append((sorted(symbol_ranges)[-1][1] + 1, len(lines)))
        for gap_start, gap_end in gaps:
            if gap_start > gap_end:
                continue
            gap_text = "\n".join(lines[gap_start - 1 : gap_end]).strip()
            if len(gap_text) >= MIN_CHUNK_CHARS:
                chunks.append((gap_start, gap_end, gap_text[:8000], "<module>"))
    if not chunks:
        return chunk_fallback(text)
    return chunks


_TS_DECL = re.compile(
    r"^(?P<indent>[ \t]*)"
    r"(?:export\s+(?:default\s+)?)?"
    r"(?:async\s+)?"
    r"(?:function\*?\s+(?P<fn>[A-Za-z_$][\w$]*)"
    r"|class\s+(?P<cls>[A-Za-z_$][\w$]*)"
    r"|(?:const|let|var)\s+(?P<var>[A-Za-z_$][\w$]*)\s*[:=]"
    r"|(?:interface|type|enum)\s+(?P<ty>[A-Za-z_$][\w$]*))",
    re.MULTILINE,
)


def chunk_ts(text: str) -> List[Chunk]:
    lines = text.splitlines()
    matches = list(_TS_DECL.finditer(text))
    if not matches:
        return chunk_fallback(text)
    chunks: List[Chunk] = []
    for i, m in enumerate(matches):
        if m.group("indent"):
            continue  # only top-level declarations
        name = m.group("fn") or m.group("cls") or m.group("var") or m.group("ty") or "?"
        start_line = text.count("\n", 0, m.start()) + 1
        end_line = (
            text.count("\n", 0, matches[i + 1].start()) + 1
            if i + 1 < len(matches)
            else len(lines) + 1
        )
        end_line = min(end_line, start_line + MAX_CHUNK_LINES)
        body = "\n".join(lines[start_line - 1 : end_line - 1])
        if len(body) >= MIN_CHUNK_CHARS:
            chunks.append((start_line, end_line - 1, body[:8000], name))
    return chunks or chunk_fallback(text)


_SHELL_FN = re.compile(r"^(?P<name>[A-Za-z_][\w]*)\s*\(\)\s*\{", re.MULTILINE)


def chunk_shell(text: str) -> List[Chunk]:
    lines = text.splitlines()
    matches = list(_SHELL_FN.finditer(text))
    if not matches:
        return chunk_fallback(text)
    chunks: List[Chunk] = []
    for m in matches:
        name = m.group("name")
        start = text.count("\n", 0, m.start()) + 1
        depth = 0
        i = start - 1
        end = start
        while i < len(lines):
            depth += lines[i].count("{") - lines[i].count("}")
            i += 1
            if depth <= 0 and i > start - 1:
                end = i
                break
        body = "\n".join(lines[start - 1 : end])
        if len(body) >= MIN_CHUNK_CHARS:
            chunks.append((start, end, body[:8000], name))
    return chunks or chunk_fallback(text)


def chunk_fallback(text: str) -> List[Chunk]:
    """Word-count window for non-code / unrecognized content."""
    lines = text.splitlines()
    if not lines:
        return []
    chunks: List[Chunk] = []
    i = 0
    while i < len(lines):
        start = i
        word_count = 0
        while i < len(lines) and word_count < 300:
            word_count += len(lines[i].split())
            i += 1
        body = "\n".join(lines[start:i]).strip()
        if body and len(body) >= MIN_CHUNK_CHARS:
            chunks.append((start + 1, i, body[:8000], ""))
        # overlap
        if i >= len(lines):
            break
        i = max(start + 1, i - 6)
    return chunks


def detect_language(path: Path) -> str:
    suf = path.suffix.lower()
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".sh": "shell",
        ".bash": "shell",
        ".zsh": "shell",
        ".md": "markdown",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".rules": "text",
    }.get(suf, "text")


def chunk_file(path: Path, text: str) -> List[Chunk]:
    lang = detect_language(path)
    if lang == "python":
        return chunk_python(text)
    if lang in ("typescript", "javascript"):
        return chunk_ts(text)
    if lang == "shell":
        return chunk_shell(text)
    return chunk_fallback(text)
