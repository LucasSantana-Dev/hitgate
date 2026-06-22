"""Functional tests for ragcore/mcp_server.py.

Covers _render(), _respond(), and the main() JSON-RPC dispatch loop.
No real index I/O: retrieval.search is mocked at the module boundary.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure ragcore/ is on the path so `import mcp_server` works the same way
# the server itself expects (mcp_server.py does sys.path.insert(0, its parent)).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ragcore"))

import mcp_server
from mcp_server import _render, _respond


# ---------------------------------------------------------------------------
# _render
# ---------------------------------------------------------------------------

_RESULT = {
    "rank": 1,
    "rrf": 0.032,
    "cos": 0.87,
    "bm25": 0.45,
    "source_type": "code",
    "repo": "hitgate",
    "symbol": "search",
    "path": "ragcore/retrieval.py",
    "start_line": 42,
    "end_line": 80,
    "text": "def search(query, top=5): ...",
}


def test_render_empty():
    assert _render([]) == "No matches."


def test_render_single_result():
    out = _render([_RESULT])
    assert "ragcore/retrieval.py" in out
    assert "rrf=0.032" in out
    assert "search" in out  # symbol
    assert "def search" in out  # snippet


def test_render_no_symbol():
    r = {**_RESULT, "symbol": None, "repo": None}
    out = _render([r])
    assert "ragcore/retrieval.py" in out
    assert "::" not in out


# ---------------------------------------------------------------------------
# _respond
# ---------------------------------------------------------------------------

def test_respond_success(capsys):
    _respond(1, result={"answer": 42})
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 1
    assert payload["result"] == {"answer": 42}
    assert "error" not in payload


def test_respond_error(capsys):
    _respond(2, error={"code": -32601, "message": "unknown method"})
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert payload["id"] == 2
    assert payload["error"]["code"] == -32601
    assert "result" not in payload


def test_respond_null_id(capsys):
    _respond(None, result="ok")
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert payload["id"] is None


# ---------------------------------------------------------------------------
# main() — JSON-RPC dispatch
# ---------------------------------------------------------------------------

def _run_main(lines: list[str], mock_search=None) -> list[dict]:
    """Feed lines to main() via stdin mock; return parsed JSON-RPC responses."""
    stdin_mock = io.StringIO("\n".join(lines) + "\n")
    captured_out = io.StringIO()
    target = mock_search or MagicMock(return_value=[])
    with patch("mcp_server.search", target), \
         patch.object(sys, "stdin", stdin_mock), \
         patch.object(sys, "stdout", captured_out):
        mcp_server.main()
    return [json.loads(l) for l in captured_out.getvalue().splitlines() if l.strip()]


def test_main_initialize():
    responses = _run_main([json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})])
    assert len(responses) == 1
    r = responses[0]
    assert r["id"] == 1
    assert r["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in r["result"]["capabilities"]


def test_main_tools_list():
    responses = _run_main([json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})])
    assert len(responses) == 1
    tools = responses[0]["result"]["tools"]
    assert any(t["name"] == "rag_query" for t in tools)


def test_main_tools_call_rag_query():
    fake_result = [{**_RESULT}]
    mock_search = MagicMock(return_value=fake_result)
    msg = json.dumps({
        "jsonrpc": "2.0", "id": 3,
        "method": "tools/call",
        "params": {"name": "rag_query", "arguments": {"query": "how does search work", "top": 3}},
    })
    responses = _run_main([msg], mock_search=mock_search)
    assert len(responses) == 1
    r = responses[0]
    assert r["result"]["isError"] is False
    assert "ragcore/retrieval.py" in r["result"]["content"][0]["text"]
    mock_search.assert_called_once()
    call_kwargs = mock_search.call_args
    assert call_kwargs.kwargs.get("query") == "how does search work"


def test_main_unknown_tool():
    msg = json.dumps({
        "jsonrpc": "2.0", "id": 4,
        "method": "tools/call",
        "params": {"name": "not_a_tool", "arguments": {}},
    })
    responses = _run_main([msg])
    assert responses[0]["error"]["code"] == -32601


def test_main_unknown_method():
    msg = json.dumps({"jsonrpc": "2.0", "id": 5, "method": "no_such_method", "params": {}})
    responses = _run_main([msg])
    assert responses[0]["error"]["code"] == -32601


def test_main_skips_blank_lines_and_notifications():
    lines = [
        "",
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 6, "method": "tools/list", "params": {}}),
    ]
    responses = _run_main(lines)
    # Only tools/list emits a response; notification and blank are silent
    assert len(responses) == 1
    assert responses[0]["id"] == 6


def test_main_search_exception_returns_error():
    mock_search = MagicMock(side_effect=RuntimeError("index not built"))
    msg = json.dumps({
        "jsonrpc": "2.0", "id": 7,
        "method": "tools/call",
        "params": {"name": "rag_query", "arguments": {"query": "anything"}},
    })
    responses = _run_main([msg], mock_search=mock_search)
    assert responses[0]["error"]["code"] == -32000
    assert "index not built" in responses[0]["error"]["message"]
