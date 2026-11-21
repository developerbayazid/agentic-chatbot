"""PostgreSQL test helpers.

The application has a single storage backend, so the suite needs a real
PostgreSQL server. Each test gets its own **disposable schema**: the schema is
created before the test and dropped afterwards, which keeps tests isolated
without paying for a database per test or risking cross-test contamination.

The schema is selected through the connection string's ``options`` parameter, so
``create_connection`` and ``init_schema`` see the isolated schema transparently —
no production code needs a test-only switch.
"""

from __future__ import annotations

import os
import uuid
from urllib.parse import quote

import psycopg
from psycopg.rows import dict_row

# Prefer the CI/dev value; fall back to the conventional local server.
TEST_DSN = os.environ.get("TEST_POSTGRES_DSN") or (
    "postgresql://postgres:postgres@127.0.0.1:5432/agentic_chatbot_test"
)


def dsn_for_schema(schema: str) -> str:
    """Return a DSN whose ``search_path`` prefers ``schema`` then ``public``.

    ``public`` stays on the path because the ``vector`` extension and its type
    live there; dropping it makes ``vector(1536)`` unresolvable.
    """
    options = quote(f"-csearch_path={schema},public", safe="")
    separator = "&" if "?" in TEST_DSN else "?"
    return f"{TEST_DSN}{separator}options={options}"


def _admin() -> psycopg.Connection:
    """An autocommit connection used only for DDL on the server."""
    return psycopg.connect(TEST_DSN, row_factory=dict_row, autocommit=True)


def create_schema() -> str:
    schema = f"t_{uuid.uuid4().hex[:12]}"
    with _admin() as admin, admin.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA "{schema}"')
    return schema


def drop_schema(schema: str) -> None:
    """Drop the test schema, failing loudly rather than hanging forever.

    A test that leaves a connection mid-transaction holds locks on this schema,
    and ``DROP SCHEMA ... CASCADE`` would then block indefinitely — turning one
    failing assertion into a suite that never finishes. A lock timeout converts
    that into a visible teardown error.
    """
    with _admin() as admin, admin.cursor() as cursor:
        cursor.execute("SET lock_timeout = '10s'")
        cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def connect(schema: str):
    """Open a connection in the test schema, using the app's connection setup.

    Tests must call ``init_schema`` on the returned connection. ``search_path`` is
    ``schema, public`` — ``public`` must stay for the pgvector type — so a query
    against an *uninitialised* schema quietly falls through to tables in
    ``public``. The ``schema`` fixture watches for that fallthrough and fails the
    test, because otherwise it silently reads data belonging to another test.
    """
    from agentic_chatbot.postgres import create_connection

    return create_connection(dsn_for_schema(schema))


APPLICATION_TABLES = frozenset(
    {
        "threads",
        "notes",
        "documents",
        "document_chunks",
        "rag_meta",
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
    }
)


def application_tables_in_public() -> set[str]:
    """The application tables currently present in the shared ``public`` schema.

    Used by the ``schema`` fixture to detect a test that never initialised its
    own schema and wrote to ``public`` instead.
    """
    with _admin() as admin, admin.cursor() as cursor:
        cursor.execute(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename = ANY(%s)",
            (list(APPLICATION_TABLES),),
        )
        return {row["tablename"] for row in cursor.fetchall()}


def truncate_all(connection) -> None:
    """Remove every application row, keeping the schema itself.

    Used by tests that exercise "init schema twice" behaviour against a schema
    that already exists.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
        )
        tables = [row["tablename"] for row in cursor.fetchall()]

        if tables:
            joined = ", ".join(f'"{name}"' for name in tables)
            cursor.execute(f"TRUNCATE {joined} RESTART IDENTITY CASCADE")

    connection.commit()
