"""LlamaIndex adapter is pure interface-mapping with no hard dep — tested with
duck-typed fakes for NodeWithScore / TextNode, mirroring test_langchain_adapter.py."""
from adapters.llamaindex_retriever import to_harness


class _Node:
    def __init__(self, meta=None, node_id=""):
        self.metadata = meta or {}
        self.id_ = node_id


class _NodeWithScore:
    def __init__(self, meta=None, node_id=""):
        self.node = _Node(meta=meta, node_id=node_id)


class _Retriever:
    """Accepts similarity_top_k kwarg — the happy path."""
    def __init__(self, nodes):
        self._nodes = nodes

    def retrieve(self, query, similarity_top_k=None):
        return self._nodes


class _LegacyRetriever:
    """Does not accept similarity_top_k — raises TypeError, triggering the fallback."""
    def __init__(self, nodes):
        self._nodes = nodes

    def retrieve(self, query):
        return self._nodes


def test_maps_file_path_metadata_to_path():
    r = to_harness(_Retriever([
        _NodeWithScore(meta={"file_path": "src/index.py"}),
        _NodeWithScore(meta={"file_path": "src/search.py"}),
    ]))
    assert r("q", top=5, scope="code") == [{"path": "src/index.py"}, {"path": "src/search.py"}]


def test_respects_top():
    r = to_harness(_Retriever([
        _NodeWithScore(meta={"file_path": "a.py"}),
        _NodeWithScore(meta={"file_path": "b.py"}),
        _NodeWithScore(meta={"file_path": "c.py"}),
    ]))
    assert r("q", top=2, scope=None) == [{"path": "a.py"}, {"path": "b.py"}]


def test_falls_back_to_node_id_when_no_metadata():
    r = to_harness(_Retriever([_NodeWithScore(meta={}, node_id="chunk-42")]))
    assert r("q", top=1, scope=None) == [{"path": "chunk-42"}]


def test_falls_back_retrieve_without_similarity_kwarg():
    """Retriever that doesn't accept similarity_top_k triggers the TypeError fallback."""
    r = to_harness(_LegacyRetriever([_NodeWithScore(meta={"file_path": "legacy.py"})]))
    assert r("q", top=1, scope=None) == [{"path": "legacy.py"}]


def test_custom_path_key():
    r = to_harness(
        _Retriever([_NodeWithScore(meta={"source": "docs/guide.md"})]),
        path_key="source",
    )
    assert r("q", top=1, scope=None) == [{"path": "docs/guide.md"}]


def test_source_metadata_fallback():
    """When file_path is absent, adapter falls back to 'source' key."""
    r = to_harness(_Retriever([_NodeWithScore(meta={"source": "README.md"})]))
    assert r("q", top=1, scope=None) == [{"path": "README.md"}]


def test_file_name_metadata_fallback():
    """When file_path and source are absent, adapter falls back to 'file_name'."""
    r = to_harness(_Retriever([_NodeWithScore(meta={"file_name": "chunkers.py"})]))
    assert r("q", top=1, scope=None) == [{"path": "chunkers.py"}]
