"""Thread lifecycle business logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentic_chatbot.models import Thread
from agentic_chatbot.repository import ThreadRepository

if TYPE_CHECKING:
    from langgraph.checkpoint.sqlite import SqliteSaver


class ThreadService:
    def __init__(
        self,
        repository: ThreadRepository,
        checkpointer: SqliteSaver,
    ):
        self._repository = repository
        self._checkpointer = checkpointer

    def create_thread(self, title: str = "New chat") -> Thread:
        return self._repository.create(title)

    def list_threads(self) -> list[Thread]:
        return self._repository.list_all()

    def get_thread(self, thread_id: str) -> Thread | None:
        return self._repository.get(thread_id)

    def thread_exists(self, thread_id: str) -> bool:
        return self._repository.exists(thread_id)

    def rename_thread(self, thread_id: str, title: str) -> None:
        self._repository.update_title(thread_id, title[:100])

    def touch_thread(self, thread_id: str) -> None:
        self._repository.touch(thread_id)

    def delete_thread(self, thread_id: str) -> bool:
        if not self._repository.exists(thread_id):
            return False

        self._checkpointer.delete_thread(thread_id)
        self._repository.delete(thread_id)
        return True
