"""The harness is retriever-agnostic. These assert the plug-in contract and the metric
math directly, with a stub retriever — no model, no index, no built-in coupling."""
import pytest

from eval.run import load_retriever, run


def test_run_is_retriever_agnostic_and_computes_metrics():
    # stub retriever: q1 answer at rank 1, q2 at rank 3, q3 missing entirely.
    canned = {
        "q1": [{"path": "src/right.py"}, {"path": "x.py"}],
        "q2": [{"path": "x.py"}, {"path": "y.py"}, {"path": "src/right.py"}],
        "q3": [{"path": "x.py"}],
    }
    stub = lambda query, top, scope: canned[query][:top]
    cases = [
        {"query": "q1", "expect_path_contains": "right.py", "expect_scope": "code"},
        {"query": "q2", "expect_path_contains": "right.py", "expect_scope": "code"},
        {"query": "q3", "expect_path_contains": "right.py", "expect_scope": "code"},
    ]
    out = run(cases, top=5, retriever=stub)
    assert out["n"] == 3
    assert out["hit@1"] == round(1 / 3, 3)      # only q1 at rank 1
    assert out["hit@3"] == round(2 / 3, 3)      # q1 + q2
    assert out["hit@5"] == round(2 / 3, 3)      # q3 never returns the answer
    assert out["mrr"] == round((1 / 1 + 1 / 3 + 0) / 3, 3)


def test_default_loads_builtin():
    r = load_retriever(None)
    assert callable(r)


def test_spec_imports_external_callable():
    r = load_retriever("eval.example_external_retriever:retrieve")
    assert callable(r)


def test_malformed_spec_exits():
    with pytest.raises(SystemExit):
        load_retriever("not-a-valid-spec")  # no ':'


def test_unknown_module_exits():
    with pytest.raises(SystemExit):
        load_retriever("nope.does.not.exist:retrieve")


def test_example_retriever_returns_protocol_shape(tmp_path, monkeypatch):
    (tmp_path / "fusion.py").write_text("def reciprocal_rank_fusion():\n    return None\n")
    (tmp_path / "other.py").write_text("def unrelated():\n    return None\n")
    monkeypatch.setenv("RAG_SOURCE_ROOTS", str(tmp_path))
    from eval.example_external_retriever import retrieve

    res = retrieve("reciprocal rank fusion", top=3, scope="code")
    assert res and all("path" in r for r in res)
    assert "fusion.py" in res[0]["path"]  # the file with the matching terms ranks first
