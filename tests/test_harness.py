"""The harness is retriever-agnostic. These assert the plug-in contract and the metric
math directly, with a stub retriever — no model, no index, no built-in coupling."""
import pytest

from hitgate.run import load_retriever, run


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
    r = load_retriever("hitgate.example_external_retriever:retrieve")
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
    from hitgate.example_external_retriever import retrieve

    res = retrieve("reciprocal rank fusion", top=3, scope="code")
    assert res and all("path" in r for r in res)
    assert "fusion.py" in res[0]["path"]  # the file with the matching terms ranks first


def test_run_validates_retriever_result_has_path_key():
    """Retriever returning result without 'path' key should raise clear ValueError."""
    stub = lambda query, top, scope: [{"content": "missing path key"}]
    cases = [
        {"query": "q1", "expect_path_contains": "right.py", "expect_scope": "code"},
    ]
    with pytest.raises(ValueError) as exc_info:
        run(cases, top=5, retriever=stub)
    assert "path" in str(exc_info.value).lower()
    assert "retriever" in str(exc_info.value).lower()


def test_run_validates_retriever_result_path_is_string():
    """Retriever returning non-string 'path' value should raise clear TypeError."""
    stub = lambda query, top, scope: [{"path": None}]
    cases = [
        {"query": "q1", "expect_path_contains": "right.py", "expect_scope": "code"},
    ]
    with pytest.raises(TypeError) as exc_info:
        run(cases, top=5, retriever=stub)
    assert "path" in str(exc_info.value).lower()
    assert "str" in str(exc_info.value).lower()


def test_run_validates_retriever_result_path_is_string_with_int():
    """Retriever returning integer 'path' value should raise clear TypeError."""
    stub = lambda query, top, scope: [{"path": 42}]
    cases = [
        {"query": "q1", "expect_path_contains": "right.py", "expect_scope": "code"},
    ]
    with pytest.raises(TypeError) as exc_info:
        run(cases, top=5, retriever=stub)
    assert "path" in str(exc_info.value).lower()
    assert "str" in str(exc_info.value).lower()


def test_run_validates_retriever_result_is_dict():
    """Retriever returning non-dict result should raise clear TypeError."""
    stub = lambda query, top, scope: ["not a dict"]
    cases = [
        {"query": "q1", "expect_path_contains": "right.py", "expect_scope": "code"},
    ]
    with pytest.raises(TypeError) as exc_info:
        run(cases, top=5, retriever=stub)
    assert "mapping" in str(exc_info.value).lower() or "dict" in str(exc_info.value).lower()
    assert "retriever" in str(exc_info.value).lower()


def test_run_validates_with_valid_retriever_still_works():
    """Valid retriever with proper shape should continue to work (regression test)."""
    canned = {
        "q1": [{"path": "src/right.py"}, {"path": "x.py"}],
    }
    stub = lambda query, top, scope: canned[query][:top]
    cases = [
        {"query": "q1", "expect_path_contains": "right.py", "expect_scope": "code"},
    ]
    out = run(cases, top=5, retriever=stub)
    assert out["n"] == 1
    assert out["hit@1"] == 1.0


# ---------------------------------------------------------------------------
# load_retriever — error handling for malformed specs
# ---------------------------------------------------------------------------


def test_load_retriever_empty_spec_returns_builtin():
    """load_retriever(None) or load_retriever('') returns the builtin retriever."""
    r = load_retriever("")
    assert callable(r)
    # It's the builtin, not an external one
    r2 = load_retriever(None)
    assert callable(r2)


def test_load_retriever_colon_only_exits():
    """load_retriever(':') (malformed spec) exits cleanly."""
    with pytest.raises(SystemExit) as exc_info:
        load_retriever(":")
    assert exc_info.value.code != 0


def test_load_retriever_no_colon_exits():
    """load_retriever('module_without_colon') exits cleanly."""
    with pytest.raises(SystemExit) as exc_info:
        load_retriever("some.module")
    assert exc_info.value.code != 0


def test_load_retriever_empty_module_exits():
    """load_retriever(':function') (empty module) exits cleanly."""
    with pytest.raises(SystemExit) as exc_info:
        load_retriever(":function")
    assert exc_info.value.code != 0


def test_load_retriever_empty_function_exits():
    """load_retriever('module:') (empty function) exits cleanly."""
    with pytest.raises(SystemExit) as exc_info:
        load_retriever("some.module:")
    assert exc_info.value.code != 0


def test_load_retriever_nonexistent_module_exits():
    """load_retriever with a non-existent module exits cleanly."""
    with pytest.raises(SystemExit) as exc_info:
        load_retriever("does.not.exist:retrieve")
    assert exc_info.value.code != 0


def test_load_retriever_nonexistent_function_exits():
    """load_retriever with an existing module but non-existent function exits."""
    with pytest.raises(SystemExit) as exc_info:
        load_retriever("hitgate.run:nonexistent_function")
    assert exc_info.value.code != 0


def test_load_retriever_non_callable_attribute_exits():
    """load_retriever when the attribute exists but isn't callable exits."""
    with pytest.raises(SystemExit) as exc_info:
        load_retriever("hitgate.run:DATASET")  # DATASET is a Path, not callable
    assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# metrics() edge cases — n=0, hit_rank None (MISS), etc.
# ---------------------------------------------------------------------------


def test_metrics_with_no_cases():
    """run() with an empty cases list computes metrics safely (no division by zero)."""
    stub = lambda query, top, scope: []
    cases = []
    out = run(cases, top=5, retriever=stub)
    assert out["n"] == 0
    # With n=0, all hit metrics should be 0.0
    assert out["hit@1"] == 0.0
    assert out["hit@3"] == 0.0
    assert out["hit@5"] == 0.0
    assert out["mrr"] == 0.0


def test_metrics_all_misses():
    """run() with all queries missing (hit_rank=None) computes 0.0 for all metrics."""
    stub = lambda query, top, scope: []  # empty results
    cases = [
        {"query": "q1", "expect_path_contains": "notfound.py", "expect_scope": "code"},
        {"query": "q2", "expect_path_contains": "notfound.py", "expect_scope": "code"},
    ]
    out = run(cases, top=5, retriever=stub)
    assert out["n"] == 2
    assert out["hit@1"] == 0.0
    assert out["hit@3"] == 0.0
    assert out["hit@5"] == 0.0
    assert out["mrr"] == 0.0


def test_metrics_mixed_hits_and_misses():
    """run() with partial hits computes correct metrics (1 hit + 1 miss)."""
    canned = {
        "q1": [{"path": "target.py"}],
        "q2": [{"path": "other.py"}],  # doesn't contain "target.py"
    }
    stub = lambda query, top, scope: canned[query][:top]
    cases = [
        {"query": "q1", "expect_path_contains": "target.py", "expect_scope": "code"},
        {"query": "q2", "expect_path_contains": "target.py", "expect_scope": "code"},
    ]
    out = run(cases, top=5, retriever=stub)
    assert out["n"] == 2
    assert out["hit@1"] == 0.5  # 1/2
    # MRR = (1/1 + 0) / 2 = 1/2 = 0.5
    assert out["mrr"] == pytest.approx(0.5, abs=0.001)


def test_metrics_hit_beyond_top_k():
    """run() should not count a hit beyond the top-k limit."""
    canned = {
        "q1": [
            {"path": "a.py"},
            {"path": "b.py"},
            {"path": "c.py"},
            {"path": "target.py"},  # rank 4, not in hit@3
        ],
    }
    stub = lambda query, top, scope: canned[query][:top]
    cases = [
        {"query": "q1", "expect_path_contains": "target.py", "expect_scope": "code"},
    ]
    out = run(cases, top=5, retriever=stub)
    assert out["n"] == 1
    assert out["hit@1"] == 0.0  # not at rank 1
    assert out["hit@3"] == 0.0  # not in top 3
    assert out["hit@5"] == 1.0  # is in top 5


def test_run_by_scope_aggregation():
    """run() aggregates metrics by scope correctly."""
    canned = {
        "q1": [{"path": "code.py"}],
        "q2": [{"path": "readme.md"}],
    }
    stub = lambda query, top, scope: canned[query][:top]
    cases = [
        {"query": "q1", "expect_path_contains": "code.py", "expect_scope": "code"},
        {"query": "q2", "expect_path_contains": "readme.md", "expect_scope": "markdown"},
    ]
    out = run(cases, top=5, retriever=stub)
    assert "by_scope" in out
    assert "code" in out["by_scope"]
    assert out["by_scope"]["code"]["n"] == 1
    assert out["by_scope"]["code"]["hit@1"] == 1.0
    assert "markdown" in out["by_scope"]
    assert out["by_scope"]["markdown"]["n"] == 1
    assert out["by_scope"]["markdown"]["hit@1"] == 1.0


def test_run_by_intent_aggregation():
    """run() aggregates metrics by intent correctly."""
    canned = {
        "q1": [{"path": "retrieval.py"}],
        "q2": [{"path": "build.py"}],
    }
    stub = lambda query, top, scope: canned[query][:top]
    cases = [
        {"query": "q1", "expect_path_contains": "retrieval.py", "expect_scope": "code", "intent": "retrieval"},
        {"query": "q2", "expect_path_contains": "build.py", "expect_scope": "code", "intent": "indexing"},
    ]
    out = run(cases, top=5, retriever=stub)
    assert "by_intent" in out
    assert "retrieval" in out["by_intent"]
    assert out["by_intent"]["retrieval"]["n"] == 1
    assert out["by_intent"]["retrieval"]["hit@1"] == 1.0
    assert "indexing" in out["by_intent"]
    assert out["by_intent"]["indexing"]["n"] == 1
