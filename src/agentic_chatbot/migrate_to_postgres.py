"""One-shot migration from the existing SQLite database into PostgreSQL.

What it moves
-------------
``threads``, ``notes``, ``documents``, ``document_chunks``, ``rag_meta`` and —
optionally — LangGraph checkpoints.

Design rules
------------
* **Idempotent.** Every insert is ``ON CONFLICT DO NOTHING`` on the table's
  primary key, so re-running after a partial failure converges instead of
  duplicating. ``document_chunks`` is the one exception: its ``row_id`` is a
  sequence value, so rows are keyed on the stable ``chunk_id`` instead.
* **Verified.** Row counts are compared per table after copying; the command
  exits non-zero if any table disagrees. A migration that silently drops rows is
  worse than no migration.
* **Non-destructive.** The SQLite file is only ever read. Nothing is deleted.
* **Bounded.** Rows are read in batches rather than loaded whole, so a large
  corpus does not have to fit in memory.

Usage::

    uv run python -m agentic_chatbot.migrate_to_postgres \
        --sqlite chatbot_memory.db \
        --dsn postgresql://postgres:postgres@127.0.0.1:5432/bayazid \
        [--checkpoints] [--dry-run]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

TABLES = ("threads", "notes", "documents", "document_chunks", "rag_meta")

# Ordered so a foreign-key-aware backend could be migrated without reordering,
# though the current schema declares no FKs.
COLUMNS: dict[str, tuple[str, ...]] = {
    "threads": ("thread_id", "title", "owner_id", "created_at", "updated_at"),
    "notes": ("note_id", "thread_id", "title", "content", "created_at"),
    "documents": (
        "doc_id",
        "namespace",
        "source",
        "title",
        "content_hash",
        "size_bytes",
        "owner_id",
        "created_at",
        "updated_at",
    ),
    "document_chunks": (
        "row_id",
        "chunk_id",
        "doc_id",
        "namespace",
        "chunk_index",
        "page",
        "content",
        "created_at",
    ),
    "rag_meta": ("key", "value"),
}

# The conflict target for each table: what makes a row "already migrated".
CONFLICT_KEY: dict[str, str] = {
    "threads": "thread_id",
    "notes": "note_id",
    "documents": "doc_id",
    # row_id comes from a sequence, so chunk_id is the durable identity.
    "document_chunks": "chunk_id",
    "rag_meta": "key",
}

BATCH = 500


@dataclass
class Report:
    copied: dict[str, int] = field(default_factory=dict)
    source_counts: dict[str, int] = field(default_factory=dict)
    target_counts: dict[str, int] = field(default_factory=dict)
    checkpoints: str = "skipped"
    vectors: str = "skipped"

    @property
    def ok(self) -> bool:
        return all(
            self.target_counts.get(table, 0) >= self.source_counts.get(table, 0)
            for table in TABLES
        )


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    """Columns that actually exist, so an older database still migrates."""
    present = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    return [column for column in COLUMNS[table] if column in present]


def _batches(
    connection: sqlite3.Connection, table: str, columns: list[str]
) -> Iterator[list[tuple[Any, ...]]]:
    cursor = connection.execute(f"SELECT {', '.join(columns)} FROM {table}")

    while True:
        rows = cursor.fetchmany(BATCH)

        if not rows:
            return

        yield [tuple(row) for row in rows]


def _count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def migrate(
    sqlite_path: str,
    dsn: str,
    *,
    include_checkpoints: bool = False,
    include_vectors: bool = False,
    faiss_dir: str = "data/faiss",
    dry_run: bool = False,
) -> Report:
    from agentic_chatbot.postgres import create_connection, init_schema

    report = Report()
    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row

    target = create_connection(dsn)
    init_schema(target)

    try:
        for table in TABLES:
            columns = _columns(source, table)
            report.source_counts[table] = _count(source, table)
            report.copied[table] = 0

            if dry_run:
                continue

            placeholders = ", ".join("%s" for _ in columns)
            key = CONFLICT_KEY[table]
            statement = (
                f"INSERT INTO {table} ({', '.join(columns)}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT ({key}) DO NOTHING"
            )

            with target.cursor() as cursor:
                for batch in _batches(source, table, columns):
                    cursor.executemany(statement, batch)
                    report.copied[table] += cursor.rowcount

            target.commit()

        if include_checkpoints and not dry_run:
            report.checkpoints = _migrate_checkpoints(sqlite_path, dsn)

        if include_vectors and not dry_run:
            report.vectors = _migrate_vectors(sqlite_path, dsn, faiss_dir)

        if not dry_run:
            _reset_sequences(target)

        for table in TABLES:
            report.target_counts[table] = _count_sql(target, table)
    finally:
        target.close()
        source.close()

    return report


def _count_sql(connection: Any, table: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS n FROM {table}")
        return int(cursor.fetchone()["n"])


def _reset_sequences(target: Any) -> None:
    """Advance BIGSERIAL sequences past the migrated ids.

    ``document_chunks`` rows are copied with their explicit ``row_id``, which does
    *not* advance the sequence. Without this, the next insert would reuse an id
    that already exists and fail with a duplicate key. ``setval`` to the current
    maximum - or to 1 when empty - makes subsequent inserts continue correctly.
    """
    with target.cursor() as cursor:
        cursor.execute(
            "SELECT setval(pg_get_serial_sequence('document_chunks', 'row_id'), "
            "GREATEST(COALESCE(MAX(row_id), 0), 1), COALESCE(MAX(row_id), 0) > 0) "
            "FROM document_chunks"
        )
    target.commit()


def _migrate_vectors(sqlite_path: str, dsn: str, directory: str = "data/faiss") -> str:
    """Copy FAISS embeddings into ``document_chunks.embedding``, keyed by row id.

    Embeddings live in the FAISS files rather than in SQLite, so they are read
    from those files and matched to rows by the id FAISS stored — which is the
    chunk's ``row_id``. A namespace whose index file is missing is reported
    rather than silently skipped; otherwise retrieval would quietly return
    nothing for it after the switch.
    """
    from agentic_chatbot.postgres import create_connection

    root = Path(directory)

    if not root.exists():
        return f"no FAISS directory at {root}"

    target = create_connection(dsn)
    copied = 0
    missing: list[str] = []

    try:
        with target.cursor() as cursor:
            cursor.execute("SELECT DISTINCT namespace FROM document_chunks")
            namespaces = [row["namespace"] for row in cursor.fetchall()]

        for namespace in namespaces:
            indexed = _read_namespace_index(root, namespace)

            if indexed is None:
                missing.append(namespace)
                continue

            ids, vectors = indexed

            with target.cursor() as cursor:
                for row_id, vector in zip(ids, vectors):
                    # `embedding IS NULL` makes this idempotent: a re-run leaves
                    # already-migrated vectors untouched instead of rewriting
                    # them, so the reported count reflects real work.
                    cursor.execute(
                        "UPDATE document_chunks SET embedding = %s "
                        "WHERE row_id = %s AND embedding IS NULL",
                        (_pg_array(vector), int(row_id)),
                    )
                    copied += cursor.rowcount

            target.commit()

        summary = f"{copied} chunk embeddings copied"

        if missing:
            summary += f"; no FAISS index for {len(missing)} namespace(s): "
            summary += ", ".join(sorted(missing)[:3])

        return summary
    finally:
        target.close()


def _read_namespace_index(
    root: Path, namespace: str
) -> tuple[list[int], list[list[float]]] | None:
    """Read one namespace's FAISS ids and vectors, or None when absent.

    Vectors are read from the underlying ``IndexFlatIP`` storage via
    ``rev_swig_ptr`` rather than ``reconstruct_n``. On this Windows build
    ``reconstruct_n`` crashes the interpreter with a native stack-buffer error
    (exit 0xC0000409) for ids stored through ``IndexIDMap2``, while the flat
    index's own contiguous array is reliable. Both return the same data; this is
    a workaround for the binding, not a change in what is migrated.
    """
    import faiss

    from agentic_chatbot.vector_store import _filename

    path = root / _filename(namespace)

    if not path.exists():
        return None

    index = faiss.read_index(str(path))

    if index.ntotal == 0:
        return [], []

    ids = faiss.vector_to_array(index.id_map)

    # IndexIDMap2 wraps the index that actually stores the vectors.
    inner = faiss.downcast_index(index.index)
    raw = faiss.rev_swig_ptr(inner.get_xb(), inner.ntotal * inner.d)
    matrix = raw.reshape(inner.ntotal, inner.d).copy()

    return [int(value) for value in ids], matrix.tolist()


def _pg_array(values: Any) -> str:
    return "{" + ",".join(repr(float(value)) for value in values) + "}"


def _migrate_checkpoints(sqlite_path: str, dsn: str) -> str:
    """Copy LangGraph checkpoints through the official savers.

    This goes through the two implementations rather than copying their internal
    tables, because the serialised payload format is the checkpointer's business,
    not ours. A shape change would otherwise corrupt resumable state silently.
    """
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.checkpoint.sqlite import SqliteSaver

    from agentic_chatbot.postgres import create_connection, run_outside_transaction

    source = sqlite3.connect(sqlite_path, check_same_thread=False)
    target = create_connection(dsn)

    threads = [
        row[0]
        for row in source.execute(
            "SELECT DISTINCT thread_id FROM checkpoints"
            if _has_table(source, "checkpoints")
            else "SELECT NULL WHERE 0"
        )
    ]

    if not threads:
        source.close()
        target.close()
        return "no checkpoints found"

    sqlite_saver = SqliteSaver(source)
    postgres_saver = PostgresSaver(target)
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    run_outside_transaction(target, postgres_saver.setup)

    migrated = 0
    failures: list[str] = []

    for thread_id in threads:
        try:
            migrated += _copy_thread(sqlite_saver, postgres_saver, thread_id)
        except Exception as error:  # noqa: BLE001 - reported, not swallowed
            # One unreadable thread must not abort the whole migration, but the
            # reason is recorded so the run cannot claim success it did not have.
            failures.append(f"{thread_id}: {type(error).__name__}: {error}")

    target.commit()
    source.close()
    target.close()

    summary = f"{migrated} checkpoints copied across {len(threads)} threads"

    if failures:
        summary += f" — {len(failures)} thread(s) failed"
        for line in failures[:3]:
            summary += f"\n  {line}"

    return summary


def _copy_thread(sqlite_saver: Any, postgres_saver: Any, thread_id: str) -> int:
    """Copy every checkpoint (and its writes) for one thread, newest first.

    Iterating all checkpoints rather than only the latest preserves the ability
    to replay history, which is what makes an interrupted conversation resumable
    on the new backend.
    """
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    copied = 0

    for item in sqlite_saver.list(config):
        item_config = item.config["configurable"]
        checkpoint = item.checkpoint
        checkpoint_id = checkpoint.get("id") or item_config.get("checkpoint_id")

        if not checkpoint_id:
            continue

        target_config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": item_config.get("checkpoint_ns", ""),
                "checkpoint_id": checkpoint_id,
            }
        }

        postgres_saver.put(
            target_config,
            checkpoint,
            item.metadata or {},
            checkpoint.get("channel_versions", {}),
        )

        if item.pending_writes:
            # `pending_writes` rows are (task_id, channel, value). The task id
            # differs per write, so writes are grouped back by it.
            grouped: dict[str, list[tuple[str, Any]]] = {}

            for write in item.pending_writes:
                task_id, channel, value = write
                grouped.setdefault(str(task_id), []).append((channel, value))

            for task_id, writes in grouped.items():
                postgres_saver.put_writes(
                    target_config, writes, task_id=task_id
                )

        copied += 1

    return copied


def _has_table(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", default="chatbot_memory.db")
    parser.add_argument("--dsn", required=True)
    parser.add_argument(
        "--checkpoints",
        action="store_true",
        help="Also copy LangGraph conversation state.",
    )
    parser.add_argument(
        "--vectors",
        action="store_true",
        help="Also copy FAISS embeddings into document_chunks.embedding.",
    )
    parser.add_argument(
        "--faiss-dir",
        default="data/faiss",
        help="Where the FAISS indexes live (default: data/faiss).",
    )
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)

    report = migrate(
        arguments.sqlite,
        arguments.dsn,
        include_checkpoints=arguments.checkpoints,
        include_vectors=arguments.vectors,
        faiss_dir=arguments.faiss_dir,
        dry_run=arguments.dry_run,
    )

    print(f"{'table':<18} {'source':>8} {'copied':>8} {'target':>8}")
    print("-" * 46)

    for table in TABLES:
        print(
            f"{table:<18} {report.source_counts[table]:>8} "
            f"{report.copied[table]:>8} {report.target_counts[table]:>8}"
        )

    print(f"\ncheckpoints: {report.checkpoints}")
    print(f"vectors    : {report.vectors}")

    if arguments.dry_run:
        print("\ndry run — nothing was written")
        return 0

    if not report.ok:
        print("\nFAILED: a table has fewer rows in Postgres than in SQLite.", file=sys.stderr)
        return 1

    print("\nOK: every table has at least as many rows in Postgres as in SQLite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
