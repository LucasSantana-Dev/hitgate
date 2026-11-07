#!/usr/bin/env python3
"""MCP stdio server exposing rag_query over the hybrid BM25+cosine index.

JSON-RPC 2.0. Supports: initialize, tools/list, tools/call (rag_query).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import traceback

from ragcore.retrieval import search

TOOL_SCHEMA = {
    "name": "rag_query",
    "description": (
        "Hybrid semantic + BM25 search over the indexed corpus: source code "
        "(Python/TS/JS/Shell), markdown docs (README, CHANGELOG, docs/**), and "
        "recent git commits across the configured source roots. Returns top-K "
        "chunks with path:line + symbol + repo citations. Auto-scopes to the "
        "current source root when cwd is inside one — pass scope_repos=['all'] "
        "to disable. Use instead of grep for fuzzy or cross-file recall."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            "scope_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "source types: code, repo-docs, repo-readme, changelog, spec, roadmap, commit",
            },
            "scope_repos": {
                "type": "array",
                "items": {"type": "string"},
                "description": "source-root names to filter by, or pass ['all'] to disable cwd auto-scoping",
            },
            "cwd": {"type": "string", "description": "working dir to drive auto-scoping (defaults to server cwd)"},
        },
        "required": ["query"],
    },
}


def _render(results: list[dict]) -> str:
    if not results:
        return "No matches."
    lines = []
    for r in results:
        tag = r["source_type"]
        if r.get("repo"):
            tag += f"/{r['repo']}"
        if r.get("symbol"):
            tag += f"::{r['symbol']}"
        lines.append(
            f"#{r['rank']}  rrf={r['rrf']} cos={r['cos']} bm={r['bm25']}  [{tag}]  {r['path']}:{r['start_line']}-{r['end_line']}"
        )
        snippet = r["text"][:500].replace("\n", " ")
        lines.append(f"  {snippet}")
    return "\n".join(lines)


def _respond(msg_id, result=None, error=None):
    out = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


def _client_message(exc: Exception) -> str:
    """Map an exception to a message safe to send to an MCP client.

    Raw exception text can carry absolute paths, model locations or library
    internals, so it never reaches the client. The full traceback goes to stderr
    (the server log) instead.
    """
    traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
    if isinstance(exc, ImportError):
        return "retrieval engine dependencies are missing: pip install 'hitgate[hybrid]'"
    if isinstance(exc, (FileNotFoundError, sqlite3.OperationalError)):
        return "index not available: build it with `python -m ragcore.build`"
    if isinstance(exc, (ValueError, TypeError)):
        return "invalid arguments for rag_query"
    return "internal error (see server log)"


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params") or {}

        if method == "initialize":
            _respond(
                msg_id,
                result={
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "rag-index", "version": "0.2.0"},
                },
            )
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            _respond(msg_id, result={"tools": [TOOL_SCHEMA]})
        elif method == "tools/call":
            tool = params.get("name")
            args = params.get("arguments") or {}
            if tool != "rag_query":
                _respond(msg_id, error={"code": -32601, "message": f"unknown tool: {tool}"})
                continue
            try:
                scope_types = args.get("scope_types") or None
                scope_repos_raw = args.get("scope_repos") or None
                if scope_repos_raw == ["all"]:
                    scope_repos = None
                    cwd = args.get("cwd")  # respect cwd hint but ignore repo match
                elif scope_repos_raw:
                    scope_repos = scope_repos_raw
                    cwd = None
                else:
                    scope_repos = None
                    cwd = args.get("cwd")
                results = search(
                    query=args.get("query", ""),
                    top=int(args.get("top") or 5),
                    scope_types=scope_types,
                    scope_repos=scope_repos,
                    cwd=cwd,
                    rerank=bool(args.get("rerank", True)),
                )
                _respond(
                    msg_id,
                    result={
                        "content": [{"type": "text", "text": _render(results)}],
                        "isError": False,
                    },
                )
            except Exception as e:  # noqa: BLE001
                _respond(msg_id, error={"code": -32000, "message": _client_message(e)})
        elif msg_id is not None:
            _respond(msg_id, error={"code": -32601, "message": f"unknown method: {method}"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
