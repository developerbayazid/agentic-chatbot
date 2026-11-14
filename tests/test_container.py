import sqlite3

import pytest

from agentic_chatbot.container import ChatbotContainer, TOOL_GUIDANCE
from agentic_chatbot.repository import DocumentsRepository, NotesRepository
from agentic_chatbot.services.chat_service import ChatService
from agentic_chatbot.services.document_service import DocumentService
from agentic_chatbot.services.thread_service import ThreadService
from agentic_chatbot.services.title_service import TitleService
from agentic_chatbot.tools.registry import STATIC_TOOLS
from agentic_chatbot.vector_store import VectorIndexStore


def _table_names(connection):
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row["name"] for row in rows}


def test_container_creates_schema_and_services(container):
    names = _table_names(container.connection)

    assert "threads" in names
    assert "notes" in names
    assert "documents" in names
    assert "document_chunks" in names
    assert "rag_meta" in names
    assert any(name.startswith("checkpoint") for name in names)
    note_columns = {
        row[1]
        for row in container.connection.execute("PRAGMA table_info(notes)")
    }
    assert "thread_id" in note_columns
    assert isinstance(container.thread_service, ThreadService)
    assert isinstance(container.title_service, TitleService)
    assert isinstance(container.chat_service, ChatService)
    assert isinstance(container.notes_repository, NotesRepository)
    assert isinstance(container.documents_repository, DocumentsRepository)
    assert isinstance(container.vector_store, VectorIndexStore)
    assert isinstance(container.document_service, DocumentService)
    assert container.vector_store.path_for("default").parent.is_dir()
    assert container.document_service._search_mode == "hybrid"
    assert container.document_service._rrf_k == 60
    tool_names = {tool.name for tool in container.tools}
    assert len(tool_names) == len(STATIC_TOOLS) + 6
    assert {
        "calculator",
        "get_current_time",
        "calculate_loan_payment",
        "save_note",
        "search_documents",
        "list_documents",
    } <= tool_names
    assert container.chat_llm is not container.llm


def test_container_thread_lifecycle(container):
    thread = container.thread_service.create_thread("Hello")

    assert [item.thread_id for item in container.thread_service.list_threads()] == [
        thread.thread_id
    ]
    assert container.chat_service.get_messages(thread.thread_id) == []

    assert container.thread_service.delete_thread(thread.thread_id) is True
    assert container.thread_service.get_thread(thread.thread_id) is None


def test_container_appends_tool_selection_guidance(container):
    content = container.chat_service._system_message.content

    assert TOOL_GUIDANCE in content
    assert "search_documents" in content
    assert "Never claim to have searched" in content
    assert container.chat_service._context_provider is not None
    assert container.chat_service._context_provider() == ""


def test_close_closes_connection(settings):
    instance = ChatbotContainer(settings)
    instance.close()

    with pytest.raises(sqlite3.ProgrammingError):
        instance.connection.execute("SELECT 1")
