import sqlite3

import pytest

from agentic_chatbot.container import ChatbotContainer
from agentic_chatbot.services.chat_service import ChatService
from agentic_chatbot.services.thread_service import ThreadService
from agentic_chatbot.services.title_service import TitleService


def _table_names(connection):
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row["name"] for row in rows}


def test_container_creates_schema_and_services(container):
    names = _table_names(container.connection)

    assert "threads" in names
    assert any(name.startswith("checkpoint") for name in names)
    assert isinstance(container.thread_service, ThreadService)
    assert isinstance(container.title_service, TitleService)
    assert isinstance(container.chat_service, ChatService)


def test_container_thread_lifecycle(container):
    thread = container.thread_service.create_thread("Hello")

    assert [item.thread_id for item in container.thread_service.list_threads()] == [
        thread.thread_id
    ]
    assert container.chat_service.get_messages(thread.thread_id) == []

    assert container.thread_service.delete_thread(thread.thread_id) is True
    assert container.thread_service.get_thread(thread.thread_id) is None


def test_close_closes_connection(settings):
    instance = ChatbotContainer(settings)
    instance.close()

    with pytest.raises(sqlite3.ProgrammingError):
        instance.connection.execute("SELECT 1")
