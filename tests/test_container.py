import psycopg
import pytest

from agentic_chatbot.container import TOOL_GUIDANCE, ChatbotContainer
from agentic_chatbot.inventory.tools import create_inventory_tools
from agentic_chatbot.pg_vector_store import PgVectorStore
from agentic_chatbot.repository import DocumentsRepository, NotesRepository
from agentic_chatbot.services.chat_service import ChatService
from agentic_chatbot.services.document_service import DocumentService
from agentic_chatbot.services.thread_service import ThreadService
from agentic_chatbot.services.title_service import TitleService
from agentic_chatbot.tools.registry import STATIC_TOOLS


def _table_names(connection, schema):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = %s",
            (schema,),
        )
        return {row["tablename"] for row in cursor.fetchall()}


def _columns(connection, schema, table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s",
            (schema, table),
        )
        return {row["column_name"] for row in cursor.fetchall()}


def test_container_creates_schema_and_services(container, schema):
    names = _table_names(container.connection, schema)

    assert "threads" in names
    assert "notes" in names
    assert "documents" in names
    assert "document_chunks" in names
    assert "rag_meta" in names
    assert any(name.startswith("checkpoint") for name in names)
    assert "thread_id" in _columns(container.connection, schema, "notes")
    assert isinstance(container.thread_service, ThreadService)
    assert isinstance(container.title_service, TitleService)
    assert isinstance(container.chat_service, ChatService)
    assert isinstance(container.notes_repository, NotesRepository)
    assert isinstance(container.documents_repository, DocumentsRepository)
    assert isinstance(container.vector_store, PgVectorStore)
    assert isinstance(container.document_service, DocumentService)
    assert container.vector_store.probe() is True
    assert container.document_service._search_mode == "hybrid"
    assert container.document_service._rrf_k == 60
    tool_names = {tool.name for tool in container.tools}
    assert container.inventory_service is not None
    assert container.inventory_store is not None
    inventory_names = {
        tool.name
        for tool in create_inventory_tools(container.inventory_service)
    }
    assert inventory_names <= tool_names
    assert len(tool_names) == len(STATIC_TOOLS) + 6 + len(inventory_names)
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

    # A closed psycopg connection raises on use rather than returning a result.
    with pytest.raises(psycopg.OperationalError):
        instance.connection.execute("SELECT 1")


def test_missing_dsn_is_reported_actionably(tmp_path):
    from agentic_chatbot.config import Settings

    settings = Settings(
        postgres_dsn="",
        inventory_data_path=str(tmp_path / "inventory.json"),
        openai_api_key="test-key",
        _env_file=None,
    )

    with pytest.raises(RuntimeError, match="POSTGRES_DSN is not set"):
        ChatbotContainer(settings)
