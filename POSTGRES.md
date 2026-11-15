# PostgreSQL

BAYAZID AI can store its relational data and conversation state in PostgreSQL
instead of SQLite. **SQLite remains the default** — an existing installation
keeps working with no configuration change.

## Should you switch?

| | SQLite (default) | PostgreSQL |
| --- | --- | --- |
| Setup | none | a server plus a DSN |
| Concurrency | one writer; the app serializes through one connection | real concurrent writers |
| Multiple app instances | **no** — single worker only | yes |
| Usage | CLI, single-user demo | multi-user deployment |

If you run one process and one operator, SQLite is fine. Switch when you need
more than one app instance, or when concurrent writers matter.

## Configuration

```bash
DATABASE_BACKEND=postgres
POSTGRES_DSN=postgresql://user:password@127.0.0.1:5432/bayazid
```

Anything else keeps using `DATABASE_PATH`. The schema is created automatically on
first start; there is no separate migration step for a fresh database.

## Migrating an existing SQLite database

The script reads SQLite and writes Postgres. It never modifies or deletes the
SQLite file.

```bash
uv run python -m agentic_chatbot.migrate_to_postgres \
    --sqlite chatbot_memory.db \
    --dsn postgresql://user:password@127.0.0.1:5432/bayazid \
    --checkpoints
```

- `--checkpoints` also copies conversation state through LangGraph's own savers,
  so interrupted conversations stay resumable. Without it, threads and documents
  move but conversation history does not.
- `--dry-run` reports what would be copied without writing.
- **Idempotent.** Safe to re-run after a partial failure; rows are matched on
  their primary key (`chunk_id` for chunks, since `row_id` comes from a
  sequence). A second run copies 0 rows.
- **Verified.** Row counts are compared per table and the command exits non-zero
  if any table ends up with fewer rows in Postgres than in SQLite.

Recommended sequence:

1. Stop the app.
2. Back up the SQLite file (a copy is enough).
3. `--dry-run` to see the expected counts.
4. Run for real with `--checkpoints`.
5. Run it again to confirm idempotency (it should copy 0 rows).
6. Start the app with `DATABASE_BACKEND=postgres` and check `/health/ready`.
7. Keep the SQLite file untouched until you are satisfied; switching back is just
   removing `DATABASE_BACKEND`.

## Things that will surprise you

**Timestamps are `TIMESTAMP` without time zone, on purpose.** SQLite stores naive
UTC text. A `TIMESTAMPTZ` column would reinterpret that text in the session's
timezone and silently shift every stored value by the server's UTC offset. The
plain type round-trips exactly, which is what makes migration parity verifiable.
Do not "correct" this to `TIMESTAMPTZ` without re-checking data written before the
change.

**One connection, one lock — same as SQLite.** The repositories share a single
connection so their statements land in one transaction, and `PostgresSaver` is
constructed on that same connection rather than opening its own. Graph state and
relational rows therefore commit together. The consequence is that the
application is still effectively single-writer per process; Postgres's benefit
here is durability and the ability to run *multiple processes*, not intra-process
parallel writes.

**`PostgresSaver.setup()` must run outside a transaction.** It issues `CREATE
INDEX CONCURRENTLY`, which Postgres refuses inside a transaction block. This is
handled by `postgres.run_outside_transaction`, which enables autocommit only for
that call. Autocommit is deliberately *not* global — that would silently disable
`rollback()` and break `replace_document`'s atomicity.

## Verifying the backend

```bash
# Repository contract against both engines (needs a scratch database)
TEST_POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:5432/bayazid_test \
  uv run pytest tests/test_storage_parity.py tests/test_postgres_container.py -q
```

Without `TEST_POSTGRES_DSN` those tests skip, so a normal test run needs no
database. The parity file asserts identical behaviour on both engines; the
container file builds a real `ChatbotContainer` on Postgres and drives thread
management, document ingest/search, and — importantly — owner isolation, which
must hold on either backend.

## Not done yet

Sprint 5 covers relational storage and checkpoints only. Vectors still live in
FAISS on disk, and BM25 is built in memory from SQL rows. Moving embeddings into
`pgvector` — and making the search path Postgres-native — is Sprint 6.
