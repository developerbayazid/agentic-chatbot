"""SQLite access for thread metadata."""

import sqlite3
import uuid

from agentic_chatbot.models import Thread

_SELECT_COLUMNS = "thread_id, title, created_at, updated_at"


def _to_thread(row: sqlite3.Row) -> Thread:
    return Thread(
        thread_id=row["thread_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ThreadRepository:
    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self._cursor = connection.cursor()

    def create(self, title: str = "New chat") -> Thread:
        thread_id = str(uuid.uuid4())
        self._cursor.execute(
            "INSERT INTO threads (thread_id, title) VALUES (?, ?)",
            (thread_id, title),
        )
        self._connection.commit()
        return self.get(thread_id)

    def get(self, thread_id: str) -> Thread | None:
        row = self._cursor.execute(
            f"SELECT {_SELECT_COLUMNS} FROM threads WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        return _to_thread(row) if row else None

    def list_all(self) -> list[Thread]:
        rows = self._cursor.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM threads
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
        return [_to_thread(row) for row in rows]

    def exists(self, thread_id: str) -> bool:
        row = self._cursor.execute(
            "SELECT 1 FROM threads WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        return row is not None

    def update_title(self, thread_id: str, title: str) -> None:
        self._cursor.execute(
            """
            UPDATE threads
            SET title = ?, updated_at = CURRENT_TIMESTAMP
            WHERE thread_id = ?
            """,
            (title, thread_id),
        )
        self._connection.commit()

    def touch(self, thread_id: str) -> None:
        self._cursor.execute(
            """
            UPDATE threads
            SET updated_at = CURRENT_TIMESTAMP
            WHERE thread_id = ?
            """,
            (thread_id,),
        )
        self._connection.commit()

    def delete(self, thread_id: str) -> None:
        self._cursor.execute(
            "DELETE FROM threads WHERE thread_id = ?",
            (thread_id,),
        )
        self._connection.commit()
