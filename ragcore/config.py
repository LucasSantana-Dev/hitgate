"""Configuration for hitgate — env-var driven, zero external deps.

Every value is overridable via an environment variable (all prefixed ``RAG_``).
The defaults make the tool usable with no setup: it indexes the current working
directory into a local ``./.rag-index/`` using a small multilingual embedding
model.

    RAG_INDEX_DIR        where the sqlite index lives          (default: .rag-index)
    RAG_SOURCE_ROOTS     os.pathsep-separated dirs to index    (default: cwd)
    RAG_EMBED_MODEL      sentence-transformers model id        (default: e5-small)
    RAG_EMBED_DIM        embedding dimensionality              (default: 384)
    RAG_MAX_FILE_BYTES   skip files larger than this           (default: 200000)
    RAG_GIT_LOG_DAYS     commit-history window to index        (default: 180)

Retrieval-time flags (RAG_HYBRID, RAG_BM25_WEIGHT, RAG_RERANK_MODEL, …) are read
in retrieval.py where they are used.
"""
from __future__ import annotations

import os
from pathlib import Path


def _int_env(name: str, default: int, minimum: int | None = None) -> int:
    """Read an int env var, or return default. Fail-fast on invalid input.

    Args:
        name: environment variable name (e.g. "RAG_EMBED_DIM")
        default: value if env var is unset
        minimum: optional lower bound; if specified, reject values <= minimum

    Returns:
        integer value

    Raises:
        ValueError: if env var is set but not a valid int, or if < minimum
    """
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        result = int(val)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {val!r}")
    if minimum is not None and result <= minimum:
        raise ValueError(f"{name} must be > {minimum}, got {result}")
    return result


def _bool_env(name: str, default: bool) -> bool:
    """Read a bool env var, or return default. Fail-fast on unrecognized values.

    Args:
        name: environment variable name (e.g. "RAG_CHUNK_CONTEXT_PREFIX")
        default: value if env var is unset

    Returns:
        boolean value

    Raises:
        ValueError: if env var is set to an unrecognized value
    """
    val = os.environ.get(name)
    if val is None:
        return default
    lower_val = val.lower()
    if lower_val in ("on", "1", "true", "yes"):
        return True
    if lower_val in ("off", "0", "false", "no"):
        return False
    raise ValueError(
        f"{name} must be one of (on, 1, true, yes, off, 0, false, no), got {val!r}"
    )


def _choice_env(name: str, default: str, choices: set[str]) -> str:
    """Read a choice env var, or return default. Fail-fast on invalid input.

    Args:
        name: environment variable name (e.g. "RAG_CHUNK_PREFIX_FORMAT")
        default: value if env var is unset
        choices: set of valid string values

    Returns:
        validated string value

    Raises:
        ValueError: if env var is set but not in choices
    """
    val = os.environ.get(name)
    if val is None:
        return default
    lower_val = val.lower()
    if lower_val in choices:
        return lower_val
    raise ValueError(
        f"{name} must be one of {sorted(choices)}, got {val!r}"
    )


def _roots(val: str) -> list[Path]:
    return [Path(p).expanduser().resolve() for p in val.split(os.pathsep) if p.strip()]


# --- index location -------------------------------------------------------
INDEX_DIR = Path(os.environ.get("RAG_INDEX_DIR", ".rag-index")).expanduser()
DB = INDEX_DIR / "index.sqlite"
QLOG = INDEX_DIR / "queries.sqlite"

# --- what to index --------------------------------------------------------
# Each root contributes its source code + markdown docs (README, CHANGELOG,
# docs/**). Default: the current working directory, so the tool indexes itself.
SOURCE_ROOTS = _roots(os.environ.get("RAG_SOURCE_ROOTS", "")) or [Path.cwd()]

# --- embedding ------------------------------------------------------------
EMBED_MODEL = os.environ.get("RAG_EMBED_MODEL", "intfloat/multilingual-e5-small")
EMBED_DIM = _int_env("RAG_EMBED_DIM", 384, minimum=0)

# --- indexing limits ------------------------------------------------------
MAX_FILE_BYTES = _int_env("RAG_MAX_FILE_BYTES", 200000, minimum=0)
GIT_LOG_DAYS = _int_env("RAG_GIT_LOG_DAYS", 180, minimum=0)

CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".sh", ".bash", ".zsh"}

# --- chunk context prefix -------------------------------------------------
# When True, prepend a context line to each chunk before embedding.
# Format is controlled by RAG_CHUNK_PREFIX_FORMAT:
#   "full"   (default) — "source_type | repo | filename | symbol"
#   "symbol"           — "source_type | symbol"  (omits repo and filename)
CHUNK_CONTEXT_PREFIX = _bool_env("RAG_CHUNK_CONTEXT_PREFIX", True)
CHUNK_PREFIX_FORMAT = _choice_env("RAG_CHUNK_PREFIX_FORMAT", "full", {"full", "symbol"})

EXCLUDED_DIR_PARTS = {
    "site-packages", "htmlcov", ".eggs", ".tox", "node_modules", "vendor",
    "dist", "build", "coverage", ".git", ".next", ".turbo", "venv", ".venv",
    "__pycache__", ".pytest_cache", ".mypy_cache", "test-results",
    "playwright-report", ".storybook", ".docusaurus", ".worktrees", "worktrees",
    ".stryker-tmp",  # Stryker JS/TS mutation-testing sandbox — duplicate source copies
    ".rag-index",
    # Test scaffolding is not part of the implementation corpus a "where is X implemented"
    # query searches — indexing it makes the retriever return tests instead of the code.
    "tests", "test", "__tests__", "spec", "specs",
}


def require_hybrid() -> None:
    """Raise a helpful error if the optional [hybrid] retrieval-engine deps are missing.

    The eval harness core is dependency-free; the bundled hybrid retriever needs
    numpy + rank-bm25 + sentence-transformers, shipped as the ``[hybrid]`` extra.
    Call this at the entry of any path that actually loads the engine, so a missing
    extra surfaces as a clear "install it" message instead of an opaque AttributeError.
    """
    import importlib.util

    missing = [
        pip_name
        for module, pip_name in (
            ("numpy", "numpy"),
            ("rank_bm25", "rank-bm25"),
            ("sentence_transformers", "sentence-transformers"),
        )
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        raise ImportError(
            "the bundled hybrid retriever needs the optional [hybrid] extra — "
            "`pip install hitgate[hybrid]` (missing: " + ", ".join(missing) + ")"
        )
