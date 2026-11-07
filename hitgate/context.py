"""Context gate: label-free regression gate for agent context (skills, memory notes).

Mines a golden set from a context root, scores it with a stdlib BM25 retriever and
reuses hitgate.run / hitgate.compare for metrics and the gate. No runtime deps.

Spec: docs/specs/2026-11-06-context-gate/spec.md. Caveat (ADR-0012): a hit proves the
phrase still reaches its own document under this retriever, not that the document is good.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Optional, Sequence

from hitgate._console import safe_stdio
from hitgate.compare import compare, print_table
from hitgate.run import load_retriever, run

CAVEAT = (
    "context gate measures discoverability under a lexical proxy retriever: "
    "a hit means the phrase still reaches its own document, not that the document is good."
)
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}
_STOP = set("the a an and or to for of in on use when with this is it as by be that from your you".split())
_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if len(t) > 1 and t not in _STOP]


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Minimal YAML front matter: scalars, `- item` lists, `[a, b]` inline lists.

    Returns (fields, body). Enough for skill and memory notes; not a YAML parser.
    Block scalars (`>-`, `|`) are joined into one line. Nested mappings (e.g. `metadata:`) are ignored.
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    fields: dict = {}
    key: Optional[str] = None
    block = False  # inside a `>-` / `|` block scalar for `key`
    for line in text[3:end].splitlines():
        if not line.strip():
            continue
        indented = line.startswith((" ", "\t"))
        if indented and key is not None and line.lstrip().startswith("- ") and fields.get(key) is None:
            fields[key] = []
        if indented and key is not None and isinstance(fields.get(key), list) and line.lstrip().startswith("- "):
            fields[key].append(_unquote(line.lstrip()[2:]))
            continue
        if indented:
            cur = fields.get(key) if key is not None else None
            if block or isinstance(cur, str) or cur is None and key is not None and ":" not in line:
                # block scalar, or a plain scalar continued on the next line(s)
                fields[key] = ((cur or "") + " " + _unquote(line.strip())).strip()
            continue  # nested mapping or unknown indentation: ignored
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        block = value in (">", ">-", "|", "|-")
        if block:
            fields[key] = ""
        elif value.startswith("[") and value.endswith("]"):
            fields[key] = [_unquote(v) for v in value[1:-1].split(",") if v.strip()]
        elif value:
            fields[key] = _unquote(value)
        else:
            fields[key] = None  # a `- item` list may follow
    return fields, text[end + 4:].lstrip("\n")


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def _phrases(value: object) -> list[str]:
    if isinstance(value, list):
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def _rel(p: Path, root: Path) -> str:
    """Root-anchored relative path: "/review/SKILL.md" is not a substring of "/code-review/SKILL.md"."""
    return "/" + p.relative_to(root).as_posix()


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def mine(root: Path) -> tuple[list[dict], dict[str, str]]:
    """Return (cases, documents). documents maps a relative path to its searchable text.

    Skills: each trigger / auto-invoke phrase is a query; the searchable text is the
    frontmatter description, which is what the model sees when it picks a skill.
    Notes (memory, agents, anything with a description): the frontmatter description is the query; the searchable text is the
    body with the frontmatter stripped, so the case is not trivially circular.
    """
    root = root.expanduser().resolve()
    cases: list[dict] = []
    docs: dict[str, str] = {}
    skill_dirs: set[Path] = set()

    for p in sorted(root.rglob("SKILL.md")):
        if SKIP_DIRS & set(p.relative_to(root).parts):
            continue
        fields, _ = parse_frontmatter(_read(p))
        desc = fields.get("description")
        if not isinstance(desc, str) or not desc:
            continue
        rel = _rel(p, root)
        skill_dirs.add(p.parent)
        docs[rel] = f"{fields.get('name', p.parent.name)} {desc}"
        for phrase in _phrases(fields.get("triggers")) + _phrases(fields.get("auto-invoke")):
            cases.append({"query": phrase, "expect_path_contains": rel, "intent": "skill-trigger"})

    for p in sorted(root.rglob("*.md")):
        if p.name == "SKILL.md" or p.parent in skill_dirs or SKIP_DIRS & set(p.relative_to(root).parts):
            continue
        fields, body = parse_frontmatter(_read(p))
        desc = fields.get("description")
        if not isinstance(desc, str) or not desc or len(tokenize(body)) < 20:
            continue
        rel = _rel(p, root)
        docs[rel] = body
        cases.append({"query": desc, "expect_path_contains": rel, "intent": "note"})

    return cases, docs


class BM25:
    """Plain BM25 over an in-memory {path: text} corpus; honours the hitgate Retriever protocol."""

    def __init__(self, docs: dict[str, str], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.paths = list(docs)
        self.tf = [Counter(tokenize(docs[p])) for p in self.paths]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 1.0
        df: Counter = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(self.paths)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def __call__(self, query: str, top: int, scope: Optional[str] = None) -> Sequence[dict]:
        q = tokenize(query)
        scored = []
        for i, path in enumerate(self.paths):
            s = 0.0
            for t in q:
                f = self.tf[i].get(t)
                if not f:
                    continue
                norm = self.k1 * (1 - self.b + self.b * self.len[i] / self.avg)
                s += self.idf[t] * f * (self.k1 + 1) / (f + norm)
            if s > 0:
                scored.append((s, path))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [{"path": p, "score": round(s, 4)} for s, p in scored[:top]]


def shadowed(result: dict) -> list[dict]:
    """Cases whose own document did not rank first, with the document that did."""
    out = []
    for c in result["per_case"]:
        if c["hit_rank"] == 1:
            continue
        top = (c["top_hit"] or "").rsplit(":", 1)[0] or None
        out.append({"query": c["query"], "expect": c["expect"], "rank": c["hit_rank"], "shadowed_by": top})
    return out


def _path(s: str) -> Path:
    return Path(s).expanduser()


def lost(result: dict, base: dict) -> list[dict]:
    """Cases that were hits in the baseline and are misses now, keyed by (query, expect).

    The aggregate gate (tol_pp over n cases) cannot see one broken skill among hundreds;
    this can. Cases absent from the baseline (new skills) are not counted.
    """
    was = {(c["query"], c["expect"]): c["hit_rank"] for c in base.get("per_case", [])}
    out = []
    for c in result["per_case"]:
        before = was.get((c["query"], c["expect"]))
        if before and not c["hit_rank"]:
            out.append({"query": c["query"], "expect": c["expect"], "was_rank": before, "now": c["top_hit"]})
    return out


def main(argv: Optional[list[str]] = None) -> int:
    safe_stdio()
    ap = argparse.ArgumentParser(prog="hitgate-context", description=__doc__.splitlines()[0])
    ap.add_argument("root", type=_path, help="context root (e.g. ~/.claude or a repo's .claude/)")
    ap.add_argument("--label", default="context")
    ap.add_argument("--baseline", type=_path, help="previous context.<label>.json to gate against")
    ap.add_argument("--tol", type=float, default=5.0, help="tolerance in percentage points")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--retriever", help="module:func honouring the hitgate Retriever protocol (default: stdlib BM25)")
    ap.add_argument("--out", type=_path, default=Path.cwd(), help="directory for context.<label>.json")
    ap.add_argument("--show", type=int, default=15, help="shadowed cases to print")
    a = ap.parse_args(argv)

    if not a.root.is_dir():
        print(f"hitgate-context: not a directory: {a.root}", file=sys.stderr)
        return 2
    cases, docs = mine(a.root)
    if not cases:
        print(
            f"hitgate-context: no skills with triggers or notes with a description under {a.root}",
            file=sys.stderr,
        )
        return 2

    retriever = load_retriever(a.retriever) if a.retriever else BM25(docs)
    result = run(cases, top=a.top, retriever=retriever)
    result["docs"] = len(docs)
    result["shadowed"] = shadowed(result)

    print(
        f"[context:{a.label}]  docs={len(docs)}  n={result['n']}  MRR={result['mrr']}  "
        f"hit@1={result['hit@1']}  hit@3={result['hit@3']}  hit@5={result['hit@5']}"
    )
    for intent, m in result["by_intent"].items():
        print(f"  {intent:<14} n={m['n']:<4} hit@1={m['hit@1']}  hit@5={m['hit@5']}")
    if result["shadowed"]:
        shown = min(a.show, len(result["shadowed"]))
        print(f"\nShadowed ({len(result['shadowed'])} of {result['n']}; showing {shown}):")
        for s in result["shadowed"][:shown]:
            rank = s["rank"] if s["rank"] else f">{a.top}"
            print(f"  {s['query']!r:<48} -> {s['expect']}  rank={rank}  first={s['shadowed_by']}")
    print(f"\n{CAVEAT}")

    a.out.mkdir(parents=True, exist_ok=True)
    out_path = a.out / f"context.{a.label}.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"wrote {out_path}")

    if a.baseline:
        try:
            base = json.loads(a.baseline.read_text())
            v = compare(result, base, a.tol)
        except (OSError, ValueError, KeyError) as e:
            print(f"hitgate-context: unusable baseline {a.baseline}: {e}", file=sys.stderr)
            return 2
        print_table(result, base, v, a.tol)
        if base.get("n") != result["n"]:
            print(f"note: case set changed, baseline n={base.get('n')} current n={result['n']}")
        v["lost"] = lost(result, base)
        if v["lost"]:
            print(f"\nNewly unreachable ({len(v['lost'])}): cases that hit in the baseline and miss now")
            for c in v["lost"][: a.show]:
                print(f"  {c['query']!r:<48} -> {c['expect']}  was rank {c['was_rank']}  first={c['now']}")
            if v["verdict"] != "regression":
                v["verdict"] = "regression"
                v["reason"] = "newly unreachable cases"
        out_path.with_name(f"context.{a.label}.verdict.json").write_text(json.dumps(v, indent=2))
        return 1 if v["verdict"] == "regression" else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
