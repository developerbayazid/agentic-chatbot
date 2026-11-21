"""Acceptance: the real services work against PostgreSQL, not just the repos.

Builds an actual ``ChatbotContainer`` and drives ``ThreadService``,
``NotesRepository`` and ``DocumentService`` through it — the same code paths the
CLI and the API use. Embeddings are a deterministic double so no network is
needed, but the checkpointer is the real ``PostgresSaver``.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def pg_container(schema, settings):
    from agentic_chatbot.container import ChatbotContainer
    from tests.fakes import FakeEmbeddings

    container = ChatbotContainer(settings)
    container.document_service._embeddings = FakeEmbeddings(
        dimensions=settings.embedding_dimensions
    )

    try:
        yield container
    finally:
        container.close()


def test_container_uses_the_postgres_checkpointer(pg_container):
    from langgraph.checkpoint.postgres import PostgresSaver

    assert isinstance(pg_container.checkpointer, PostgresSaver)


def test_thread_service_round_trip(pg_container):
    threads = pg_container.thread_service

    created = threads.create_thread("Postgres thread", owner_id="alice")
    assert threads.thread_exists(created.thread_id)

    threads.rename_thread(created.thread_id, "Renamed")
    assert threads.get_thread(created.thread_id).title == "Renamed"

    assert [t.thread_id for t in threads.list_threads(owner_id="alice")] == [
        created.thread_id
    ]

    assert threads.delete_thread(created.thread_id) is True
    assert threads.thread_exists(created.thread_id) is False


def test_document_ingest_and_search_on_postgres(pg_container, tmp_path):
    """The full RAG path: read, chunk, embed, store in Postgres, then retrieve."""
    document = tmp_path / "handbook.txt"
    document.write_text(
        "The BAYAZID handbook says expense claims are due within 30 days.\n\n"
        "The onboarding guide describes laptop setup and account access.",
        encoding="utf-8",
    )

    chunks, skipped, warning = pg_container.document_service.ingest_file(
        document, namespace="default"
    )

    assert skipped is False
    assert warning is None
    assert chunks > 0

    hits = pg_container.document_service.search("How long do expense claims take?")

    assert hits, "expected at least one chunk back from Postgres-backed search"
    assert any("30 days" in hit.content for hit in hits)


def test_owner_isolation_holds_on_postgres(pg_container, tmp_path):
    """The critical security property, proven through the full stack."""
    service = pg_container.document_service

    alice_file = tmp_path / "alice.txt"
    alice_file.write_text("Alice's private salary review notes.", encoding="utf-8")
    bob_file = tmp_path / "bob.txt"
    bob_file.write_text("Bob's private salary review notes.", encoding="utf-8")

    service.ingest_file(alice_file, namespace="default", owner_id="alice")
    service.ingest_file(bob_file, namespace="default", owner_id="bob")

    alice = service.search("salary review", owner_id="alice")
    bob = service.search("salary review", owner_id="bob")

    assert alice and bob
    assert all("Alice" in hit.content for hit in alice)
    assert all("Bob" in hit.content for hit in bob)
    # Alice must never see Bob's chunk, and vice versa.
    assert not any("Bob" in hit.content for hit in alice)
    assert not any("Alice" in hit.content for hit in bob)


def test_stats_reflect_postgres_rows(pg_container, tmp_path):
    document = tmp_path / "invoices.txt"
    document.write_text("One document about invoices.", encoding="utf-8")
    pg_container.document_service.ingest_file(document, namespace="default")

    stats = pg_container.documents_repository.stats()

    assert stats["documents"] == 1
    assert stats["chunks"] >= 1


def test_deleting_a_thread_removes_its_checkpoints_for_good(settings):
    """Deleting a thread must remove its history durably, not just visibly.

    ``ThreadService.delete_thread`` removes the checkpoints and then the thread
    row; the row delete commits, which is what makes the checkpoint removal
    durable. This pins that behaviour end to end.
    """
    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.graph import END, START, MessagesState, StateGraph

    from agentic_chatbot.container import ChatbotContainer

    def respond(_state):
        return {"messages": [AIMessage(content="reply")]}

    def write_turn(container, thread_id: str) -> None:
        builder = StateGraph(MessagesState)
        builder.add_node("respond", respond)
        builder.add_edge(START, "respond")
        builder.add_edge("respond", END)
        graph = builder.compile(checkpointer=container.checkpointer)
        graph.invoke(
            {"messages": [HumanMessage(content="hello")]},
            config={"configurable": {"thread_id": thread_id}},
        )

    def checkpoint_exists(container, thread_id: str) -> bool:
        return (
            container.checkpointer.get_tuple(
                {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
            )
            is not None
        )

    first = ChatbotContainer(settings)
    try:
        thread = first.thread_service.create_thread("Bye", owner_id=None)
        write_turn(first, thread.thread_id)
        assert checkpoint_exists(first, thread.thread_id)

        assert first.thread_service.delete_thread(thread.thread_id) is True
        assert not checkpoint_exists(first, thread.thread_id)
    finally:
        first.close()

    second = ChatbotContainer(settings)
    try:
        assert not checkpoint_exists(second, thread.thread_id)
        assert not second.thread_service.thread_exists(thread.thread_id)
    finally:
        second.close()


def test_checkpoints_persist_across_containers(settings):
    """Graph state must survive a restart: it lives in the same database.

    This is the regression guard for a real bug: ``PostgresSaver`` issues its
    statements but never commits, and this application's connection is not
    autocommit, so psycopg discarded every checkpoint on close. Chat history
    survived within a process and vanished across a restart.
    """
    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.graph import END, START, MessagesState, StateGraph

    from agentic_chatbot.container import ChatbotContainer

    def respond(state):
        return {"messages": [AIMessage(content="persisted reply")]}

    thread_id = "persisted-thread"
    config = {"configurable": {"thread_id": thread_id}}

    def run_once() -> None:
        builder = StateGraph(MessagesState)
        builder.add_node("respond", respond)
        builder.add_edge(START, "respond")
        builder.add_edge("respond", END)

        graph = builder.compile(checkpointer=first.checkpointer)
        graph.invoke({"messages": [HumanMessage(content="hello")]}, config=config)

    first = ChatbotContainer(settings)
    try:
        run_once()
        stored = first.chat_service.get_messages(thread_id)
        assert stored, "the checkpoint should be readable in the same process"
    finally:
        first.close()

    second = ChatbotContainer(settings)
    try:
        restored = second.chat_service.get_messages(thread_id)
        assert [message.content for message in restored] == [
            "hello",
            "persisted reply",
        ]
    finally:
        second.close()
