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


def create_connection(database_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(
        database_path,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    return connection


def init_schema(connection: sqlite3.Connection) -> None:
    connection.execute(THREADS_TABLE_SCHEMA)
    connection.commit()
