#!/usr/bin/env python3
"""Bootstrap a golden evaluation set from your corpus.

Heuristic mode (zero deps — default): walks source files, extracts candidate
query/expect pairs from docstrings, symbol names, and module-level text.

LLM mode (opt-in, --llm): feeds each chunk to an OpenAI-compatible API to
produce a richer paraphrase query alongside the identifier query. Uses stdlib
urllib — no additional package required. Requires OPENAI_API_KEY (or set
OPENAI_BASE_URL to point at a local model).

Output is the same .jsonl that eval/run.py --dataset already consumes. Curation
helper fields (prefixed _) are silently ignored by the harness.

Usage:
    # Heuristic (zero deps):
    RAG_SOURCE_ROOTS="$PWD" python eval/generate.py --output eval/candidates.jsonl

    # LLM-enhanced (identifier + paraphrase per chunk):
    OPENAI_API_KEY=sk-... python eval/generate.py --llm --output eval/candidates.jsonl

    # Skip files already covered by an existing golden set:
    python eval/generate.py --existing eval/golden.demo.jsonl --output eval/candidates.jsonl

    # Curate the output, then run the eval:
    python eval/run.py --dataset eval/candidates.jsonl --label my-baseline
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ragcore"))

from build import is_excluded_path, iter_code_sources  # noqa: E402
from chunkers import chunk_file  # noqa: E402
from config import CODE_EXTS, MAX_FILE_BYTES, SOURCE_ROOTS  # noqa: E402

# ── query helpers ────────────────────────────────────────────────────────────

_CAMEL_RE = re.compile(r"([a-z])([A-Z])")
_TRIPLE_QUOTE_RE = re.compile(r'"""(.*?)"""|\'\'\'(.*?)\'\'\'', re.DOTALL)
_COMMENT_LINE_RE = re.compile(r"^\s*#\s*(.+)", re.MULTILINE)


def _to_words(name: str) -> str:
    """chunk_python -> chunk python, getUserProfile -> get user profile."""
    name = _CAMEL_RE.sub(r"\1 \2", name)
    return name.replace("_", " ").lower().strip()


def _extract_docstring(text: str) -> Optional[str]:
    """First meaningful sentence from a triple-quoted string in the chunk."""
    m = _TRIPLE_QUOTE_RE.search(text[:1000])
    if not m:
        return None
    raw = (m.group(1) or m.group(2) or "").strip()
    for line in raw.splitlines():
        line = line.strip()
        if len(line) >= 25:
            return line.rstrip(".")
    return None


def _first_comment(text: str) -> Optional[str]:
    """First inline comment that looks like a description (≥25 chars)."""
    for m in _COMMENT_LINE_RE.finditer(text[:600]):
        line = m.group(1).strip()
        if len(line) >= 25 and not line.startswith("type:") and "noqa" not in line:
            return line
    return None


def _heuristic(symbol: str, chunk_text: str, filename: str) -> tuple[str, str]:
    """Return (query, confidence: 'high'|'medium'|'low')."""
    docstring = _extract_docstring(chunk_text)
    if docstring and len(docstring) >= 25:
        return docstring, "high"

    if symbol and symbol != "<module>":
        words = _to_words(symbol)
        comment = _first_comment(chunk_text)
        if comment:
            # e.g. "chunk python — splits files into AST-based passages"
            query = f"{words} — {comment[:80]}"
        else:
            query = f"{words} in {filename}"
        return query, "medium"

    # <module> chunk: try first comment, fall back to first non-trivial line
    comment = _first_comment(chunk_text)
    if comment:
        return comment, "low"

    for line in chunk_text.splitlines():
        line = line.strip()
        if len(line) >= 25 and not line.startswith("#") and not line.startswith("import"):
            return line[:100], "low"

    return "", "low"


# ── intent classifier ────────────────────────────────────────────────────────

def _infer_intent(path: Path) -> str:
    name = path.stem.lower()
    if any(kw in name for kw in ("retriev", "query", "search", "rank")):
        return "retrieval"
    if any(kw in name for kw in ("build", "chunk", "embed", "index")):
        return "indexing"
    return "infrastructure"


# ── LLM call ─────────────────────────────────────────────────────────────────

def _llm_queries(
    chunk_text: str,
    filename: str,
    symbol: str,
    model: str,
    base_url: str,
    api_key: str,
) -> Optional[dict]:
    """Call an OpenAI-compatible API; return {identifier, paraphrase} or None."""
    sym_hint = f" (symbol: `{symbol}`)" if symbol and symbol != "<module>" else ""
    prompt = (
        f"You generate retrieval evaluation cases for a code search system.\n\n"
        f"Code chunk from `{filename}`{sym_hint}:\n\n"
        f"```\n{chunk_text[:1500]}\n```\n\n"
        "Generate exactly 2 search queries that should retrieve this file:\n"
        "1. identifier — uses exact technical terms, names, or identifiers from the code (8–15 words)\n"
        "2. paraphrase — natural language a developer might type who doesn't know the codebase (10–25 words)\n\n"
        "Rules: uniquely targets THIS file; no yes/no questions; "
        "starts with what/where/how/which or describes the concept directly.\n\n"
        'Respond with ONLY valid JSON: {"identifier": "...", "paraphrase": "..."}'
    )
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 200,
    }).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"].strip()
        content = re.sub(r"^```(?:json)?\n?", "", content).strip()
        content = re.sub(r"\n?```$", "", content).strip()
        parsed = json.loads(content)
        if "identifier" in parsed and "paraphrase" in parsed:
            return parsed
    except Exception:
        pass
    return None


# ── core generator ────────────────────────────────────────────────────────────

def generate(
    existing_path: Optional[Path] = None,
    llm: bool = False,
    llm_model: str = "gpt-4o-mini",
    llm_base_url: str = "https://api.openai.com/v1",
    min_confidence: str = "low",
    limit: int = 0,
    roots: Optional[list[Path]] = None,
) -> list[dict]:
    """Walk source roots, emit candidate golden cases.

    roots: override SOURCE_ROOTS from config (useful in tests and scripts that
    want to specify the corpus without setting RAG_SOURCE_ROOTS).
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if llm and not api_key:
        print("ERROR: --llm requires OPENAI_API_KEY to be set", file=sys.stderr)
        sys.exit(1)

    # Files already covered in an existing golden set
    covered: set[str] = set()
    if existing_path and existing_path.is_file():
        with existing_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        case = json.loads(line)
                        ep = case.get("expect_path_contains", "")
                        if ep:
                            covered.add(ep)
                    except json.JSONDecodeError:
                        pass
        print(f"Skipping {len(covered)} already-covered file(s) from {existing_path.name}", file=sys.stderr)

    confidence_rank = {"high": 2, "medium": 1, "low": 0}
    min_rank = confidence_rank.get(min_confidence, 0)

    candidates: list[dict] = []
    if roots is not None:
        # Caller-supplied roots: walk directly, bypassing SOURCE_ROOTS from config
        effective_roots = [Path(r).resolve() for r in roots]
        all_files: list[tuple[str, Path]] = []
        for root in effective_roots:
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
                all_files.append(("code", p))
        files = all_files
    else:
        files = iter_code_sources()
    print(f"Scanning {len(files)} source file(s)…", file=sys.stderr)

    for _stype, path in files:
        filename = path.name
        if filename in covered:
            continue

        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue

        chunks = chunk_file(path, text)
        intent = _infer_intent(path)

        for start_line, end_line, chunk_text, symbol in chunks:
            if len(chunk_text.strip()) < 60:
                continue

            query, confidence = _heuristic(symbol, chunk_text, filename)
            if not query or confidence_rank[confidence] < min_rank:
                continue

            base_case = {
                "expect_path_contains": filename,
                "expect_scope": "code",
                "intent": intent,
                "_symbol": symbol or "<module>",
                "_confidence": confidence,
                "_source": "heuristic",
                "_start_line": start_line,
            }

            if llm:
                result = _llm_queries(chunk_text, filename, symbol, llm_model, llm_base_url, api_key)
                if result:
                    if result.get("identifier"):
                        candidates.append({
                            "query": result["identifier"],
                            **base_case,
                            "_query_type": "identifier",
                            "_source": "llm",
                        })
                    if result.get("paraphrase"):
                        candidates.append({
                            "query": result["paraphrase"],
                            **base_case,
                            "_query_type": "paraphrase",
                            "_source": "llm",
                            "paraphrase": True,
                        })
                    continue  # LLM succeeded; skip heuristic fallback

            candidates.append({"query": query, "_query_type": "identifier", **base_case})

        if limit and len(candidates) >= limit:
            candidates = candidates[:limit]
            break

    return candidates


# ── output ───────────────────────────────────────────────────────────────────

# Fields the harness reads; strip everything else before writing the clean .jsonl
_HARNESS_FIELDS = {"query", "expect_path_contains", "expect_scope", "intent", "paraphrase"}


def _harness_fields(case: dict) -> dict:
    return {k: v for k, v in case.items() if k in _HARNESS_FIELDS}


def _full_fields(case: dict) -> dict:
    return case


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", default="eval/candidates.jsonl",
                    help="path to write candidate cases (default: eval/candidates.jsonl)")
    ap.add_argument("--existing", metavar="JSONL",
                    help="existing golden set; files already covered will be skipped")
    ap.add_argument("--llm", action="store_true",
                    help="use an LLM to generate identifier + paraphrase queries per chunk "
                         "(requires OPENAI_API_KEY; OPENAI_BASE_URL for non-OpenAI endpoints)")
    ap.add_argument("--llm-model", default="gpt-4o-mini",
                    help="model name passed to the API (default: gpt-4o-mini)")
    ap.add_argument("--min-confidence", choices=["high", "medium", "low"], default="medium",
                    help="minimum heuristic confidence to include (default: medium)")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap total output cases (0 = no limit)")
    ap.add_argument("--full", action="store_true",
                    help="include curation helper fields (_symbol, _confidence, …) in output")
    args = ap.parse_args()

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

    candidates = generate(
        existing_path=Path(args.existing) if args.existing else None,
        llm=args.llm,
        llm_model=args.llm_model,
        llm_base_url=base_url,
        min_confidence=args.min_confidence,
        limit=args.limit,
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    serialise = _full_fields if args.full else _harness_fields
    with out.open("w") as f:
        for case in candidates:
            f.write(json.dumps(serialise(case)) + "\n")

    by_conf: dict[str, int] = {}
    by_src: dict[str, int] = {}
    for c in candidates:
        by_conf[c.get("_confidence", "?")] = by_conf.get(c.get("_confidence", "?"), 0) + 1
        by_src[c.get("_source", "?")] = by_src.get(c.get("_source", "?"), 0) + 1

    print(f"\nWrote {len(candidates)} candidate case(s) → {out}", file=sys.stderr)
    print(f"  by confidence : {by_conf}", file=sys.stderr)
    print(f"  by source     : {by_src}", file=sys.stderr)
    print(f"\nNext steps:", file=sys.stderr)
    print(f"  1. Review and curate {out}", file=sys.stderr)
    print(f"  2. python eval/run.py --dataset {out} --label baseline-v1", file=sys.stderr)
    print(f"  3. cp eval/baseline-v1.json eval/baseline.<project>.json", file=sys.stderr)
    print(f"  4. bash eval/check.sh eval/<run>.json eval/baseline.<project>.json", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
