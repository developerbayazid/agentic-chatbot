import uuid

import pytest

from agentic_chatbot.database import create_connection, init_schema
from agentic_chatbot.repository import ThreadRepository
from agentic_chatbot.services.thread_service import ThreadService
from tests.fakes import FakeCheckpointer


@pytest.fixture
def thread_service(tmp_path):
    connection = create_connection(str(tmp_path / "threads.db"))
    init_schema(connection)
    checkpointer = FakeCheckpointer()
    service = ThreadService(ThreadRepository(connection), checkpointer)

    try:
        yield service, connection, checkpointer
    finally:
        connection.close()


def test_create_thread_defaults(thread_service):
    service, _connection, _checkpointer = thread_service

    thread = service.create_thread()

    uuid.UUID(thread.thread_id)
    assert thread.title == "New chat"
    assert thread.created_at
    assert thread.updated_at
    assert service.thread_exists(thread.thread_id)


def test_create_thread_with_custom_title(thread_service):
    service, _connection, _checkpointer = thread_service

    thread = service.create_thread("Custom chat")

    assert thread.title == "Custom chat"


def test_get_missing_thread_returns_none(thread_service):
    service, _connection, _checkpointer = thread_service

    assert service.get_thread("does-not-exist") is None
    assert service.thread_exists("does-not-exist") is False


def test_rename_truncates_to_100_characters(thread_service):
    service, _connection, _checkpointer = thread_service
    thread = service.create_thread()

    service.rename_thread(thread.thread_id, "x" * 150)

    assert service.get_thread(thread.thread_id).title == "x" * 100


def test_touch_updates_last_activity(thread_service):
    service, connection, _checkpointer = thread_service
    thread = service.create_thread()

    connection.execute(
        "UPDATE threads SET updated_at = '2000-01-01 00:00:00' WHERE thread_id = ?",
        (thread.thread_id,),
    )
    connection.commit()

    service.touch_thread(thread.thread_id)

    assert service.get_thread(thread.thread_id).updated_at != "2000-01-01 00:00:00"


def test_list_threads_orders_by_last_update(thread_service):
    service, connection, _checkpointer = thread_service
    first = service.create_thread("First")
    second = service.create_thread("Second")

    connection.execute(
        "UPDATE threads SET updated_at = '2020-01-01 00:00:00' WHERE thread_id = ?",
        (first.thread_id,),
    )
    connection.execute(
        "UPDATE threads SET updated_at = '2021-01-01 00:00:00' WHERE thread_id = ?",
        (second.thread_id,),
    )
    connection.commit()

    assert [thread.thread_id for thread in service.list_threads()] == [
        second.thread_id,
        first.thread_id,
    ]


def test_delete_thread_removes_checkpoints_and_metadata(thread_service):
    service, _connection, checkpointer = thread_service
    thread = service.create_thread()

    deleted = service.delete_thread(thread.thread_id)

    assert deleted is True
    assert checkpointer.deleted == [thread.thread_id]
    assert service.thread_exists(thread.thread_id) is False


def test_delete_missing_thread_returns_false(thread_service):
    service, _connection, checkpointer = thread_service

    assert service.delete_thread("does-not-exist") is False
    assert checkpointer.deleted == []
