"""The LangChain adapter is pure interface-mapping, so it's tested with fake Documents —
no LangChain install required (it duck-types `.invoke` / `.metadata` / `.page_content`)."""
from adapters.langchain_retriever import to_harness


class _Doc:
    def __init__(self, source=None, content="", meta=None):
        self.metadata = meta if meta is not None else ({"source": source} if source else {})
        self.page_content = content


class _Invokable:
    def __init__(self, docs):
        self._docs = docs

    def invoke(self, query):
        return self._docs


class _Legacy:
    def __init__(self, docs):
        self._docs = docs

    def get_relevant_documents(self, query):
        return self._docs


def test_maps_metadata_source_to_path():
    r = to_harness(_Invokable([_Doc("a/x.py"), _Doc("b/y.py")]))
    assert r("q", top=5, scope="code") == [{"path": "a/x.py"}, {"path": "b/y.py"}]


def test_respects_top():
    r = to_harness(_Invokable([_Doc("a.py"), _Doc("b.py"), _Doc("c.py")]))
    assert r("q", top=2, scope=None) == [{"path": "a.py"}, {"path": "b.py"}]


def test_falls_back_to_page_content_without_source():
    r = to_harness(_Invokable([_Doc(source=None, content="inline-id")]))
    assert r("q", top=1, scope=None) == [{"path": "inline-id"}]


def test_supports_legacy_get_relevant_documents():
    r = to_harness(_Legacy([_Doc("z.py")]))
    assert r("q", top=1, scope=None) == [{"path": "z.py"}]


def test_custom_path_key():
    r = to_harness(_Invokable([_Doc(meta={"file_path": "custom/p.py"})]), path_key="file_path")
    assert r("q", top=1, scope=None) == [{"path": "custom/p.py"}]
