"""Cross-user retrieval isolation: another user's chunks never surface.

The filter runs on each retriever's ranking *before* Reciprocal Rank Fusion, so
an unauthorized chunk can neither be returned nor influence the order of an
authorized one.
"""

import json

import pytest

from agentic_chatbot.pg_vector_store import PgVectorStore
from agentic_chatbot.repository import DocumentsRepository
from agentic_chatbot.services.document_service import DocumentService
from agentic_chatbot.tools.documents import create_document_tools
from tests.fakes import FakeEmbeddings
from tests.pg import connect

ALICE_TEXT = "alpha secret handbook onboarding"
BOB_TEXT = "beta confidential onboarding"


def _service(schema, mode="hybrid"):
    from agentic_chatbot.postgres import init_schema

    connection = connect(schema)
    init_schema(connection, embedding_dimensions=8)
    repository = DocumentsRepository(connection)
    service = DocumentService(
        repository,
        PgVectorStore(connection, dimensions=8),
        FakeEmbeddings(dimensions=8),
        chunk_size=200,
        chunk_overlap=0,
        top_k=4,
        # Isolation must not depend on the sign of a cosine score. The fake
        # embedding is a hash, so similarity between unrelated texts is
        # arbitrary and often negative; a 0.0 floor would drop a user's own
        # chunk for reasons that have nothing to do with ownership.
        min_score=-1.0,
        search_mode=mode,
        vector_candidates=10,
        bm25_candidates=10,
        rrf_k=60,
    )
    return service, repository, connection


def _ingest(service, root, name, text, namespace, owner_id):
    path = root / name
    path.write_text(text, encoding="utf-8")
    service.ingest_path(path, namespace, owner_id=owner_id)
    return path


@pytest.fixture
def shared(schema, tmp_path):
    service, repository, connection = _service(schema)

    try:
        _ingest(service, tmp_path, "alice.md", ALICE_TEXT, "shared", "alice")
        _ingest(service, tmp_path, "bob.md", BOB_TEXT, "shared", "bob")
        yield service, repository, tmp_path
    finally:
        connection.close()


@pytest.mark.parametrize("mode", ["hybrid", "vector", "bm25"])
def test_each_user_only_retrieves_their_own_chunks(schema, tmp_path, mode):
    service, _, connection = _service(schema, mode)

    try:
        _ingest(service, tmp_path, "alice.md", ALICE_TEXT, "shared", "alice")
        _ingest(service, tmp_path, "bob.md", BOB_TEXT, "shared", "bob")

        alice = service.search("onboarding", owner_id="alice")
        bob = service.search("onboarding", owner_id="bob")

        assert alice, "alice should retrieve her own document"
        assert bob, "bob should retrieve his own document"
        assert {hit.content for hit in alice} == {ALICE_TEXT} or all(
            "alpha" in hit.content for hit in alice
        )
        assert all("beta" not in hit.content for hit in alice)
        assert all("alpha" not in hit.content for hit in bob)
        assert {hit.namespace for hit in alice} == {"shared"}
    finally:
        connection.close()


def test_retrieval_without_an_owner_still_spans_everything(shared):
    """The CLI keeps its global behaviour: owner_id=None filters nothing."""
    service, _, _ = shared

    hits = service.search("onboarding")
    contents = " ".join(hit.content for hit in hits)

    assert "alpha" in contents
    assert "beta" in contents


def test_an_foreign_user_does_not_change_authorized_results(shared):
    """Bob's documents must not perturb what Alice retrieves or its order."""
    service, _, tmp_path = shared

    alice_alone = service.search("omboarding alpha", owner_id="alice")

    # Bob ingests more of the same kind of text into the identical namespace.
    _ingest(service, tmp_path, "bob2.md", "alpha onboarding copy", "shared", "bob")
    alice_after = service.search("omboarding alpha", owner_id="alice")

    assert [hit.chunk_id for hit in alice_after] == [
        hit.chunk_id for hit in alice_alone
    ]
    assert [hit.score for hit in alice_after] == [
        hit.score for hit in alice_alone
    ]


def test_namespace_listing_is_owner_scoped(shared):
    service, _, _ = shared

    assert service.list_namespaces(owner_id="alice") == ["shared"]
    assert service.list_namespaces(owner_id="carol") == []
    assert "shared" in service.list_namespaces()


def test_requesting_someone_elses_namespace_returns_nothing(shared):
    service, _, tmp_path = shared

    _ingest(service, tmp_path, "bob.md", BOB_TEXT, "bob-private", "bob")

    assert service.search("onboarding", "bob-private", owner_id="alice") == []


def test_owner_filtering_spans_namespaces(shared):
    service, _, tmp_path = shared

    _ingest(service, tmp_path, "alice2.md", ALICE_TEXT, "alice-home", "alice")

    hits = service.search("onboarding", owner_id="alice")

    assert hits
    assert {hit.namespace for hit in hits} == {"shared", "alice-home"}
    assert all("beta" not in hit.content for hit in hits)


def test_search_documents_tool_reads_identity_from_config(shared):
    service, _, _ = shared
    tools = {tool.name: tool for tool in create_document_tools(service)}
    search = tools["search_documents"]

    alice = json.loads(
        search.invoke(
            {"query": "onboarding", "namespace": "shared"},
            {"configurable": {"rag_owner_id": "alice"}},
        )
    )
    bob = json.loads(
        search.invoke(
            {"query": "onboarding", "namespace": "shared"},
            {"configurable": {"rag_owner_id": "bob"}},
        )
    )

    alice_text = json.dumps(alice["results"])
    bob_text = json.dumps(bob["results"])

    assert alice["count"] >= 1
    assert "alpha" in alice_text
    assert "beta" not in alice_text
    assert "beta" in bob_text
    assert "alpha" not in bob_text


def test_owner_id_is_not_a_tool_argument(shared):
    """The model cannot choose whose documents it reads."""
    service, _, _ = shared
    tools = {tool.name: tool for tool in create_document_tools(service)}

    for name in ("search_documents", "list_documents"):
        assert "owner_id" not in tools[name].args
        assert "rag_owner_id" not in tools[name].args


def test_tool_without_identity_keeps_global_behaviour(shared):
    service, _, _ = shared
    tools = {tool.name: tool for tool in create_document_tools(service)}

    payload = json.loads(
        tools["search_documents"].invoke(
            {"query": "onboarding", "namespace": "shared"}
        )
    )

    assert payload["count"] >= 2


def test_list_documents_tool_is_owner_scoped(shared):
    service, _, tmp_path = shared

    _ingest(service, tmp_path, "alice2.md", ALICE_TEXT, "alice-home", "alice")
    tools = {tool.name: tool for tool in create_document_tools(service)}

    listed = json.loads(
        tools["list_documents"].invoke(
            {}, {"configurable": {"rag_owner_id": "alice"}}
        )
    )

    namespaces = set(listed["namespaces"])
    assert namespaces == {"shared", "alice-home"}
    assert all(
        document["namespace"] != "bob-private"
        for document in listed["documents"]
    )


def test_chat_service_propagates_the_owner_into_the_run_config():
    from agentic_chatbot.services.chat_service import ChatService
    from tests.fakes import FakeThreadService, FakeTitleService

    class RecordingChatbot:
        def __init__(self):
            self.configs = []
            self.messages = []

        def get_state(self, config):
            self.configs.append(config)
            from types import SimpleNamespace

            return SimpleNamespace(values={"messages": list(self.messages)})

        def stream(self, inputs, config, stream_mode, version):
            self.configs.append(config)
            return iter(())

    chatbot = RecordingChatbot()
    service = ChatService(
        chatbot, FakeThreadService(), FakeTitleService(), "prompt"
    )

    list(service.stream_turn("thread-1", "hello", owner_id="alice"))
    list(service.resume_turn("thread-1", {"action": "reject"}, owner_id="bob"))
    service.get_pending_interrupt("thread-1", owner_id="alice")

    rag_owners = [
        config["configurable"].get("rag_owner_id") for config in chatbot.configs
    ]

    assert "alice" in rag_owners
    assert "bob" in rag_owners
    assert all(config["configurable"]["thread_id"] == "thread-1" for config in chatbot.configs)


def test_chat_service_config_is_unchanged_without_an_owner():
    from agentic_chatbot.services.chat_service import ChatService
    from tests.fakes import FakeThreadService, FakeTitleService

    service = ChatService(object(), FakeThreadService(), FakeTitleService(), "p")

    assert service.get_config("thread-1") == {"configurable": {"thread_id": "thread-1"}}
    assert service.get_config("thread-1", "alice") == {
        "configurable": {"thread_id": "thread-1", "rag_owner_id": "alice"}
    }
