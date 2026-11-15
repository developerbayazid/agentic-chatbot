# PostgreSQL

BAYAZID AI stores its relational data, conversation state, **and embeddings** in
PostgreSQL. SQLite remains available (`DATABASE_BACKEND=sqlite`) for offline use
and as the migration source, but Postgres is the default.

## Configuration

```bash
DATABASE_BACKEND=postgres
POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:5432/bayazid
```

The schema is created automatically on first start.

## What moved

| Concern | Before | Now (Postgres backend) |
| --- | --- | --- |
| Threads, notes, documents, chunks | SQLite | `threads`, `notes`, `documents`, `document_chunks` |
| Conversation state | `SqliteSaver` | `PostgresSaver` |
| Embeddings | FAISS files on disk | `document_chunks.embedding` |
| BM25 corpus | rebuilt in memory from SQL rows | unchanged — still rebuilt in memory |
| ERP demo data | JSON file | unchanged — deliberately still JSON |

## Embeddings are arrays, not pgvector — and why

`document_chunks.embedding` is `DOUBLE PRECISION[]`, not `vector(1536)`.

**pgvector is not installed here**, and cannot be: `CREATE EXTENSION vector`
returns *"extension is not available"*, and there is no C toolchain on this
machine to build it from source. A `vector` column would simply not work, so the
honest options were an array column or leaving retrieval on FAISS.

What that buys and costs:

- **Buys:** vectors live in the same rows, transaction, and backup as the chunks
  they describe. No side-car files to drift or lose. Owner filtering happens in
  the same query that scores, so a foreign chunk still cannot be returned or
  reorder an authorised one.
- **Costs:** search is a scan over the namespace's chunks rather than an indexed
  approximate search. Fine for hundreds or low thousands of chunks; it will need
  pgvector well before millions.

Vectors are L2-normalised before storage, exactly as FAISS received them
(`IndexFlatIP` on normalised vectors *is* cosine similarity), so scores from
either backend are directly comparable and tests assert the equivalence.

### Upgrading to pgvector later

The interface is deliberately identical, so this is mechanical:

1. Install pgvector, then `CREATE EXTENSION vector`.
2. `ALTER TABLE document_chunks ADD COLUMN vec vector(1536)` and backfill from
   `embedding` (already normalised).
3. Add an HNSW index.
4. Change `PgVectorStore.search`'s `ORDER BY` to `ORDER BY vec <=> %s::vector`.
5. Swap the column name in `_write`.

`DocumentService`, RRF fusion, and every caller stay untouched.

## Migrating an existing SQLite database

```bash
uv run python -m agentic_chatbot.migrate_to_postgres \
    --sqlite chatbot_memory.db \
    --dsn postgresql://postgres:postgres@127.0.0.1:5432/bayazid \
    --checkpoints \
    --vectors
```

- `--checkpoints` copies conversation state through LangGraph's own savers.
- `--vectors` copies FAISS embeddings into `document_chunks.embedding`. Without
  it the rows move but search returns nothing, so it is worth passing.
  `--faiss-dir` overrides the default `data/faiss`.
- `--dry-run` reports what would be copied without writing.
- **Idempotent.** Rows match on their primary key, and vector writes skip rows
  that already have an embedding, so a second run reports `0 copied`.
- **Verified.** Row counts are compared per table and the command exits non-zero
  if any table ends up short.

Recommended sequence: stop the app, back up the SQLite file, `--dry-run`, run
for real, run again to confirm idempotency, then start with
`DATABASE_BACKEND=postgres` and check `/health/ready`. Keep the SQLite file until
you are satisfied; switching back is just an environment change.

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
