"""Langfuse adapter is tested with a mock client — no langfuse install required."""
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_golden_jsonl(tmp_path: Path) -> Path:
    cases = [
        {
            "query": "how are chunks stored",
            "expect_path_contains": "build.py",
            "expect_scope": "code",
            "intent": "indexing",
        },
        {
            "query": "what drives ranked fusion of two lists",
            "expect_path_contains": "retrieval.py",
            "expect_scope": "code",
            "intent": "retrieval",
            "paraphrase": True,
        },
    ]
    p = tmp_path / "golden.jsonl"
    p.write_text("\n".join(json.dumps(c) for c in cases))
    return p


def _make_results_json(tmp_path: Path) -> Path:
    results = {
        "n": 2,
        "mrr": 0.75,
        "hit@5": 1.0,
        "per_case": [
            {
                "query": "how are chunks stored",
                "scope": "code",
                "intent": "indexing",
                "hit_rank": 1,
                "top_hit": "ragcore/build.py:42",
            },
            {
                "query": "what drives ranked fusion of two lists",
                "scope": "code",
                "intent": "retrieval",
                "hit_rank": 3,
                "top_hit": "ragcore/retrieval.py:88",
            },
        ],
    }
    p = tmp_path / "run.json"
    p.write_text(json.dumps(results))
    return p


def _build_mock_lf(golden_path: Path, num_items: int):
    """Return a mock Langfuse client with dataset.items matching the golden file."""
    mock_lf = MagicMock()

    cases = [json.loads(l) for l in golden_path.read_text().splitlines() if l.strip()]

    items = []
    for i, case in enumerate(cases):
        item = MagicMock()
        item.input = {"query": case["query"]}
        ctx = MagicMock()
        trace = MagicMock()
        ctx.__enter__ = MagicMock(return_value=trace)
        ctx.__exit__ = MagicMock(return_value=False)
        item.observe = MagicMock(return_value=ctx)
        items.append(item)

    dataset = MagicMock()
    dataset.items = items
    mock_lf.get_dataset = MagicMock(return_value=dataset)
    return mock_lf, items


def _patch_langfuse(mock_lf):
    """Inject a fake langfuse module so the adapter's lazy import succeeds."""
    fake_module = types.ModuleType("langfuse")
    fake_module.Langfuse = MagicMock(return_value=mock_lf)
    return patch.dict(sys.modules, {"langfuse": fake_module})


def test_creates_dataset_items(tmp_path):
    from adapters.langfuse_eval import push

    golden = _make_golden_jsonl(tmp_path)
    results = _make_results_json(tmp_path)
    mock_lf, _ = _build_mock_lf(golden, 2)

    with _patch_langfuse(mock_lf):
        push(golden, results, run_name="test-run", langfuse_client=mock_lf)

    assert mock_lf.create_dataset.call_count == 1
    assert mock_lf.create_dataset_item.call_count == 2


def test_records_run_per_item(tmp_path):
    from adapters.langfuse_eval import push

    golden = _make_golden_jsonl(tmp_path)
    results = _make_results_json(tmp_path)
    mock_lf, items = _build_mock_lf(golden, 2)

    with _patch_langfuse(mock_lf):
        push(golden, results, run_name="my-run", langfuse_client=mock_lf)

    for item in items:
        item.observe.assert_called_once_with(run_name="my-run")


def test_scores_hit_at_k(tmp_path):
    from adapters.langfuse_eval import push

    golden = _make_golden_jsonl(tmp_path)
    results = _make_results_json(tmp_path)
    mock_lf, items = _build_mock_lf(golden, 2)

    with _patch_langfuse(mock_lf):
        push(golden, results, run_name="r", langfuse_client=mock_lf)

    # First item: rank 1 — hit@1, hit@3, hit@5 all 1.0
    trace0 = items[0].observe.return_value.__enter__.return_value
    score_calls_0 = {c.kwargs["name"]: c.kwargs["value"] for c in trace0.score.call_args_list}
    assert score_calls_0["hit@1"] == 1.0
    assert score_calls_0["hit@3"] == 1.0
    assert score_calls_0["hit@5"] == 1.0
    assert score_calls_0["mrr_contribution"] == pytest.approx(1.0)

    # Second item: rank 3 — hit@1=0, hit@3=1, hit@5=1
    trace1 = items[1].observe.return_value.__enter__.return_value
    score_calls_1 = {c.kwargs["name"]: c.kwargs["value"] for c in trace1.score.call_args_list}
    assert score_calls_1["hit@1"] == 0.0
    assert score_calls_1["hit@3"] == 1.0
    assert score_calls_1["hit@5"] == 1.0
    assert score_calls_1["mrr_contribution"] == pytest.approx(1.0 / 3)


def test_miss_scores_zero(tmp_path):
    from adapters.langfuse_eval import push

    # Override results: second case is a miss (hit_rank=None)
    golden = _make_golden_jsonl(tmp_path)
    results = {
        "n": 2,
        "per_case": [
            {"query": "how are chunks stored", "scope": "code", "intent": "indexing", "hit_rank": 1, "top_hit": "build.py:1"},
            {"query": "what drives ranked fusion of two lists", "scope": "code", "intent": "retrieval", "hit_rank": None, "top_hit": ""},
        ],
    }
    results_path = tmp_path / "run.json"
    results_path.write_text(json.dumps(results))

    mock_lf, items = _build_mock_lf(golden, 2)

    with _patch_langfuse(mock_lf):
        push(golden, results_path, run_name="r", langfuse_client=mock_lf)

    trace1 = items[1].observe.return_value.__enter__.return_value
    score_calls = {c.kwargs["name"]: c.kwargs["value"] for c in trace1.score.call_args_list}
    assert score_calls["hit@1"] == 0.0
    assert score_calls["hit@5"] == 0.0
    assert score_calls["mrr_contribution"] == 0.0


def test_missing_langfuse_raises(tmp_path):
    from adapters.langfuse_eval import push

    golden = _make_golden_jsonl(tmp_path)
    results = _make_results_json(tmp_path)

    with patch.dict(sys.modules, {"langfuse": None}):
        with pytest.raises(ImportError, match="langfuse is not installed"):
            push(golden, results, run_name="r")


def test_flushes_after_run(tmp_path):
    from adapters.langfuse_eval import push

    golden = _make_golden_jsonl(tmp_path)
    results = _make_results_json(tmp_path)
    mock_lf, _ = _build_mock_lf(golden, 2)

    with _patch_langfuse(mock_lf):
        push(golden, results, run_name="r", langfuse_client=mock_lf)

    mock_lf.flush.assert_called_once()
