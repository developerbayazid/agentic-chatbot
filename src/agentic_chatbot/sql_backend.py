"""A minimal adapter that presents one cursor API over SQLite or PostgreSQL.

The repositories were written against ``sqlite3``: ``?`` placeholders, ``last
rowid``, ``rowcount``, and mapping rows. Rather than keep two copies of ~500
lines of SQL, this adapter absorbs the handful of differences so the query text
is written once and every service above it is unaware of the backend.

Differences it absorbs
----------------------
* placeholders — ``?`` → ``%s`` for psycopg
* generated ids — SQLite has ``cursor.lastrowid``; Postgres needs ``RETURNING``,
  which the caller requests explicitly via ``execute(..., returning=...)``
* timestamps — psycopg returns ``datetime``; SQLite returned text. Rows are
  normalised back to the ``"YYYY-MM-DD HH:MM:SS"`` text the models expect.

What it deliberately does *not* hide: transactions. Both drivers commit and roll
back the same way, so the repositories keep calling those directly.
"""

from __future__ import annotations

import datetime as dt
import re
import sqlite3
from typing import Any, Iterable, Mapping

import psycopg

_PLACEHOLDER = re.compile(r"\?")

# SQLite's `CURRENT_TIMESTAMP` is UTC. Postgres's is resolved in the server's
# timezone, so it is rewritten to the UTC wall clock to keep stored values
# identical between backends (and therefore comparable during migration).
_CURRENT_TIMESTAMP = re.compile(r"\bCURRENT_TIMESTAMP\b", re.IGNORECASE)
_CURRENT_TIMESTAMP_PG = "(now() AT TIME ZONE 'UTC')"


def is_postgres(connection: Any) -> bool:
    return isinstance(connection, psycopg.Connection)


def render(sql: str, postgres: bool) -> str:
    """Translate the portable SQL dialect for the target driver."""
    if not postgres:
        return sql

    return _CURRENT_TIMESTAMP.sub(
        _CURRENT_TIMESTAMP_PG, _PLACEHOLDER.sub("%s", sql)
    )


def normalize_value(value: Any) -> Any:
    """Render a value in the form the models and API have always received.

    SQLite's ``CURRENT_TIMESTAMP`` yields naive UTC text, ``"2026-11-15
    09:00:00"``. Postgres returns an *aware* ``datetime`` in the session's
    timezone, so formatting it directly would silently shift the wall clock by
    the server's UTC offset (and comparisons against the SQLite text would fail).

    Aware values are therefore converted to UTC before formatting, which
    reproduces SQLite's output exactly. A naive value is already in the shape
    SQLite produced and is left alone.
    """
    if isinstance(value, dt.datetime):
        if value.tzinfo is not None:
            value = value.astimezone(dt.timezone.utc)

        return value.strftime("%Y-%m-%d %H:%M:%S")

    return value


class Cursor:
    """Cursor facade shared by both drivers."""

    def __init__(self, connection: Any) -> None:
        self._postgres = is_postgres(connection)
        self._raw = connection.cursor()
        self._lastrowid: int | None = None

    def execute(
        self,
        sql: str,
        params: Iterable[Any] = (),
        *,
        returning: str | None = None,
    ) -> "Cursor":
        """Run one statement.

        ``returning`` names a column to read back for a generated id. On SQLite
        the value comes from ``lastrowid``; on Postgres the statement gets a
        ``RETURNING`` clause appended, because inserting the clause there is the
        only way to learn the id.
        """
        if self._postgres and returning is not None:
            self._raw.execute(f"{render(sql, True)} RETURNING {returning}", tuple(params))
            row = self._raw.fetchone()
            self._lastrowid = None if row is None else int(row[returning])
            return self

        self._raw.execute(render(sql, self._postgres), tuple(params))

        if not self._postgres:
            self._lastrowid = self._raw.lastrowid

        return self

    @property
    def lastrowid(self) -> int | None:
        return self._lastrowid

    @property
    def rowcount(self) -> int:
        return self._raw.rowcount

    def fetchone(self) -> Mapping[str, Any] | None:
        row = self._raw.fetchone()
        return _normalize_row(row)

    def fetchall(self) -> list[Mapping[str, Any]]:
        return [_normalize_row(row) for row in self._raw.fetchall()]

    def close(self) -> None:
        self._raw.close()


def _normalize_row(row: Any) -> Any:
    if row is None:
        return None

    # dict_row (psycopg) and sqlite3.Row both support keyed access; neither is a
    # plain dict, so copy through the keys to keep call sites unchanged.
    if isinstance(row, dict):
        return {key: normalize_value(value) for key, value in row.items()}

    return {key: normalize_value(row[key]) for key in row.keys()}


class Connection:
    """Connection facade: exposes ``cursor``, ``commit`` and ``rollback``."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def cursor(self) -> Cursor:
        return Cursor(self._raw)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()

    @property
    def raw(self) -> Any:
        return self._raw


def wrap(connection: Any) -> Connection:
    """Accept either a raw driver connection or an already-wrapped one."""
    return connection if isinstance(connection, Connection) else Connection(connection)


def sqlite_backend(connection: Any) -> bool:
    return isinstance(connection, sqlite3.Connection)
