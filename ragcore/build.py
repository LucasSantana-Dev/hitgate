#!/usr/bin/env python3
"""Chunk + embed configured source roots into a local sqlite index.

For each root in ``RAG_SOURCE_ROOTS`` (see config.py) this indexes:
  - source code (language-aware chunking by symbol where possible)
  - markdown docs: README, CHANGELOG, docs/**/*.md
  - recent git commits (subject + body head), if the root is a git repo

Usage:
  build.py                                   # full rebuild of all roots
  build.py --no-code                         # docs + commits only
  build.py --incremental <file> [...files]   # reindex specific files
"""
from __future__ import annotations

import argparse
import hashlib
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

try:
    import numpy as np
except ImportError:  # numpy ships with the optional [hybrid] extra
    np = None  # type: ignore[assignment]

sys.path.insert(0, str(Path(__file__).parent))
from chunkers import chunk_file, detect_language
from config import (
    CHUNK_CONTEXT_PREFIX,
    CHUNK_PREFIX_FORMAT,
    CODE_EXTS,
    DB,
    EMBED_DIM as DIM,
    EMBED_MODEL as MODEL_NAME,
    EXCLUDED_DIR_PARTS,
    GIT_LOG_DAYS,
    INDEX_DIR,
    MAX_FILE_BYTES,
    SOURCE_ROOTS,
    require_hybrid,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
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
);
CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path);
CREATE INDEX IF NOT EXISTS chunks_type ON chunks(source_type);
CREATE INDEX IF NOT EXISTS chunks_repo ON chunks(repo);
"""


def is_excluded_path(relative_path: Path) -> bool:
    for part in relative_path.parts:
        if part in EXCLUDED_DIR_PARTS:
            return True
        if part.startswith(".venv") or part.startswith(".wt-"):
            return True
    return False


def classify_repo(path: Path) -> str | None:
    rp = path.resolve()
    for root in SOURCE_ROOTS:
        for base in (root, root.resolve()):
            try:
                rp.relative_to(base)
                return root.name
            except ValueError:
                continue
    return None


def classify_type(path: Path) -> str:
    s = str(path)
    name = path.name.lower()
    if name.startswith("readme"):
        return "repo-readme"
    if name == "changelog.md":
        return "changelog"
    if s.endswith("docs/roadmap.md"):
        return "roadmap"
    if "/docs/specs/" in s and s.endswith(".md"):
        return "spec"
    if "/docs/" in s and s.endswith(".md"):
        return "repo-docs"
    if path.suffix.lower() in CODE_EXTS:
        return "code"
    if s.endswith(".md"):
        return "repo-docs"
    return "other"


def iter_md_sources() -> list[tuple[str, Path]]:
    """README / CHANGELOG / docs markdown across all source roots."""
    results: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for root in SOURCE_ROOTS:
        if not root.is_dir():
            continue
        candidates: list[Path] = []
        for name in ("README.md", "readme.md", "CHANGELOG.md"):
            p = root / name
            if p.is_file():
                candidates.append(p)
        docs = root / "docs"
        if docs.is_dir():
            candidates.extend(p for p in docs.rglob("*.md") if p.is_file())
        for p in candidates:
            rp = p.resolve()
            if rp in seen:
                continue
            try:
                if is_excluded_path(p.relative_to(root)):
                    continue
            except ValueError:
                pass
            seen.add(rp)
            results.append((classify_type(p), p))
    return results


def iter_code_sources() -> list[tuple[str, Path]]:
    results: list[tuple[str, Path]] = []
    for root in SOURCE_ROOTS:
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in CODE_EXTS:
                continue
            if is_excluded_path(p.relative_to(root)):
                continue
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            results.append(("code", p))
    return results


def collect_commit_chunks() -> list[dict]:
    """Run git log on each source root; one chunk per commit (subject + body head)."""
    rows: list[dict] = []
    for root in SOURCE_ROOTS:
        if not (root / ".git").exists():
            continue
        try:
            proc = subprocess.run(
                [
                    "git", "-C", str(root), "log",
                    f"--since={GIT_LOG_DAYS}.days", "--no-merges",
                    "--pretty=format:%H%x01%ai%x01%an%x01%s%x01%b%x02",
                ],
                capture_output=True, text=True, check=True, timeout=30,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            continue
        for entry in proc.stdout.split("\x02"):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split("\x01", 4)
            if len(parts) < 4:
                continue
            sha, date_str, author, subject = parts[:4]
            body = parts[4] if len(parts) == 5 else ""
            body_top = "\n".join(body.strip().splitlines()[:6])[:1200]
            text = f"{subject}\n\n{body_top}".strip()
            rows.append(
                {
                    "source_type": "commit",
                    "repo": root.name,
                    "language": "git",
                    "symbol": sha[:7],
                    "path": f"git:{root.name}@{sha}",
                    "start": 0,
                    "end": 0,
                    "text": text[:4000],
                    "sha": sha,
                    "mtime": 0.0,
                    "meta": f"{author} · {date_str}",
                }
            )
    return rows


def file_sha(path: Path) -> str:
    h = hashlib.sha1()
    h.update(path.read_bytes())
    return h.hexdigest()


def connect() -> sqlite3.Connection:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL"); conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(SCHEMA)
    return conn


def embed(model, texts: list[str]) -> np.ndarray:
    # E5 requires a "passage: " prefix for indexed chunks; added at embed time only.
    prefixed_texts = [f"passage: {t}" for t in texts]
    vecs = model.encode(
        prefixed_texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
    )
    return vecs.astype(np.float32)


def index_files(
    conn: sqlite3.Connection, model, files: list[tuple[str, Path]], purge_paths: list[str]
) -> int:
    for p in purge_paths:
        conn.execute("DELETE FROM chunks WHERE path = ?", (p,))
    total = 0
    batch_texts: list[str] = []
    batch_meta: list[dict] = []
    for stype, path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        sha = file_sha(path)
        mtime = path.stat().st_mtime
        repo = classify_repo(path)
        language = detect_language(path)
        for start, end, body, symbol in chunk_file(path, text):
            if CHUNK_CONTEXT_PREFIX:
                if CHUNK_PREFIX_FORMAT == "symbol":
                    context_prefix = f"{stype} | {symbol or ''}"
                else:
                    context_prefix = f"{stype} | {repo or ''} | {path.name} | {symbol or ''}"
                contextualized_text = f"{context_prefix}\n{body[:4000]}"
            else:
                contextualized_text = body[:4000]
            batch_texts.append(contextualized_text)
            batch_meta.append(
                {
                    "source_type": stype,
                    "repo": repo,
                    "language": language,
                    "symbol": symbol,
                    "path": str(path),
                    "start": start,
                    "end": end,
                    "text": body[:4000],
                    "sha": sha,
                    "mtime": mtime,
                }
            )
            if len(batch_texts) >= 64:
                _flush(conn, model, batch_texts, batch_meta)
                total += len(batch_texts)
                batch_texts.clear()
                batch_meta.clear()
    if batch_texts:
        _flush(conn, model, batch_texts, batch_meta)
        total += len(batch_texts)
    conn.commit()
    return total


def _flush(conn, model, texts, meta):
    vecs = embed(model, texts)
    rows = []
    for m, vec in zip(meta, vecs):
        rows.append(
            (
                m["source_type"], m["repo"], m["language"], m["symbol"], m["path"],
                m["start"], m["end"], m["text"], m["sha"], m["mtime"], vec.tobytes(),
            )
        )
    conn.executemany(
        "INSERT INTO chunks (source_type, repo, language, symbol, path, start_line, end_line, text, file_sha, mtime, embedding) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--incremental", nargs="+", help="specific files to reindex")
    ap.add_argument("--no-code", action="store_true", help="skip source code ingestion")
    args = ap.parse_args()

    require_hybrid()
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME)
    conn = connect()
    started = time.time()

    if args.incremental:
        targets: list[tuple[str, Path]] = []
        purge: list[str] = []
        for raw in args.incremental:
            p = Path(raw).expanduser().resolve()
            purge.append(str(p))
            if not p.exists():
                continue
            targets.append((classify_type(p), p))
        written = index_files(conn, model, targets, purge)
        print(f"incremental: {len(targets)} files, {written} chunks, {time.time()-started:.1f}s")
    else:
        conn.execute("DELETE FROM chunks")
        md_files = iter_md_sources()
        code_files = [] if args.no_code else iter_code_sources()
        written = index_files(conn, model, md_files + code_files, [])
        commits_written = 0
        if not args.no_code:
            commit_rows = collect_commit_chunks()
            for i in range(0, len(commit_rows), 64):
                batch = commit_rows[i : i + 64]
                contextualized_texts = [f"commit | {r['repo']}\n{r['text']}" for r in batch]
                vecs = embed(model, contextualized_texts)
                sql_rows = [
                    (
                        m["source_type"], m["repo"], m["language"], m["symbol"], m["path"],
                        m["start"], m["end"], m["text"], m["sha"], m["mtime"], vec.tobytes(),
                    )
                    for m, vec in zip(batch, vecs)
                ]
                conn.executemany(
                    "INSERT INTO chunks (source_type, repo, language, symbol, path, start_line, end_line, text, file_sha, mtime, embedding) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    sql_rows,
                )
                commits_written += len(batch)
            conn.commit()
        print(
            f"full rebuild: md={len(md_files)} code={len(code_files)} "
            f"commits={commits_written} chunks={written+commits_written} t={time.time()-started:.1f}s"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
