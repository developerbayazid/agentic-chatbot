"""SQLite connection and schema setup."""

import sqlite3

THREADS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    thread_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New chat',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

NOTES_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    note_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

NOTES_THREAD_INDEX = """
CREATE INDEX IF NOT EXISTS idx_notes_thread_id ON notes (thread_id)
"""


def create_connection(database_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(
        database_path,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    return connection


def init_schema(connection: sqlite3.Connection) -> None:
    connection.execute(THREADS_TABLE_SCHEMA)
    connection.execute(NOTES_TABLE_SCHEMA)
    _migrate_notes_thread_id(connection)
    connection.execute(NOTES_THREAD_INDEX)
    connection.commit()


def _migrate_notes_thread_id(connection: sqlite3.Connection) -> None:
    """Add thread_id to notes created before notes were thread-scoped.

    Older rows are kept with an empty thread_id, which means they are not
    visible from any conversation.
    """
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(notes)")
    }

    if "thread_id" not in columns:
        connection.execute(
            "ALTER TABLE notes ADD COLUMN thread_id TEXT NOT NULL DEFAULT ''"
        )
