"""A minimal cursor adapter over PostgreSQL.

The repositories are written against a portable subset of SQL: ``?``
placeholders, ``rowcount``, and mapping rows. This module absorbs the three
places where psycopg differs so the query text stays readable and every service
above the repository layer is unaware of the driver.

Differences it absorbs
----------------------
* placeholders — ``?`` → ``%s`` for psycopg
* generated ids — the caller requests them explicitly via
  ``execute(..., returning="row_id")``
* timestamps — psycopg returns ``datetime``; rows are normalised back to the
  ``"YYYY-MM-DD HH:MM:SS"`` text the models and API have always used

What it deliberately does *not* hide: transactions. The repositories call
``commit`` and ``rollback`` directly.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Mapping
from typing import Any

_PLACEHOLDER = re.compile(r"\?")

# Postgres's `CURRENT_TIMESTAMP` is resolved in the server's timezone, so it is
# rewritten to the UTC wall clock. Stored values then match what the application
# has always written, and they stay comparable across deployments.
_CURRENT_TIMESTAMP = re.compile(r"\bCURRENT_TIMESTAMP\b", re.IGNORECASE)
_CURRENT_TIMESTAMP_PG = "(now() AT TIME ZONE 'UTC')"


def render(sql: str) -> str:
    """Translate the portable SQL dialect for psycopg."""
    return _CURRENT_TIMESTAMP.sub(_CURRENT_TIMESTAMP_PG, _PLACEHOLDER.sub("%s", sql))


def normalize_value(value: Any) -> Any:
    """Render a value in the form the models and API have always received.

    Postgres returns an *aware* ``datetime`` in the session's timezone, so
    formatting it directly would shift the wall clock by the server's UTC
    offset. Aware values are converted to UTC before formatting; a naive value is
    already in the shape the application produced and is left alone.
    """
    if isinstance(value, dt.datetime):
        if value.tzinfo is not None:
            value = value.astimezone(dt.UTC)

        return value.strftime("%Y-%m-%d %H:%M:%S")

    return value


class Cursor:
    """Cursor facade over psycopg."""

    def __init__(self, connection: Any) -> None:
        self._raw = connection.cursor()
        self._lastrowid: int | None = None

    def execute(
        self,
        sql: str,
        params: Iterable[Any] = (),
        *,
        returning: str | None = None,
    ) -> Cursor:
        """Run one statement.

        ``returning`` names a column to read back for a generated id. The clause
        is appended here because it is the only way to learn the id of an
        inserted row.
        """
        if returning is not None:
            self._raw.execute(f"{render(sql)} RETURNING {returning}", tuple(params))
            row = self._raw.fetchone()
            self._lastrowid = None if row is None else int(row[returning])
            return self

        self._raw.execute(render(sql), tuple(params))

        return self

    @property
    def lastrowid(self) -> int | None:
        return self._lastrowid

    @property
    def rowcount(self) -> int:
        return self._raw.rowcount

    def fetchone(self) -> Mapping[str, Any] | None:
        return _normalize_row(self._raw.fetchone())

    def fetchall(self) -> list[Mapping[str, Any]]:
        return [_normalize_row(row) for row in self._raw.fetchall()]

    def close(self) -> None:
        self._raw.close()


def _normalize_row(row: Any) -> Any:
    if row is None:
        return None

    # dict_row gives a plain dict; copy through the keys so call sites are
    # unaffected by the driver's row type.
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
    """Accept either a raw psycopg connection or an already-wrapped one."""
    return connection if isinstance(connection, Connection) else Connection(connection)
