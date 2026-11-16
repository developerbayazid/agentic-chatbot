# PostgreSQL

BAYAZID AI stores its relational data, conversation state, **and embeddings** in
PostgreSQL. SQLite remains available (`DATABASE_BACKEND=sqlite`) for offline use
and as the migration source, but Postgres is the default.

## Configuration

```bash
DATABASE_BACKEND=postgres
POSTGRES_DSN=postgresql://USER:PASSWORD@HOST:5432/DATABASE
```

There is **no default DSN**. A connection string contains credentials, so none is
committed to the repository; the application refuses to start on the Postgres
backend until `POSTGRES_DSN` is set. Put the real value in `.env` (gitignored) or
in your platform's secret manager.

The schema is created automatically on first start.

## What moved

| Concern | Before | Now (Postgres backend) |
| --- | --- | --- |
| Threads, notes, documents, chunks | SQLite | `threads`, `notes`, `documents`, `document_chunks` |
| Conversation state | `SqliteSaver` | `PostgresSaver` |
| Embeddings | FAISS files on disk | `document_chunks.embedding` |
| BM25 corpus | rebuilt in memory from SQL rows | unchanged — still rebuilt in memory |
| ERP demo data | JSON file | unchanged — deliberately still JSON |

## Embeddings use pgvector

`document_chunks.embedding_vec` is a `vector(1536)` column with an **HNSW index**
(`vector_cosine_ops`), and search is `ORDER BY embedding_vec <=> query` — an
indexed approximate nearest-neighbour scan returning cosine similarity
(`1 - distance`).

pgvector 0.8.7 for PostgreSQL 18 is installed on this machine's server. If it is
ever missing, `PgVectorStore` detects that at construction and transparently falls
back to the older `document_chunks.embedding DOUBLE PRECISION[]` column with
in-SQL similarity. Both paths normalise queries identically and return comparable
scores, so retrieval thresholds behave the same; only performance differs.

Enabling the extension on an existing database needs no re-ingest: `init_schema`
adds the column and index, then copies existing arrays across once.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Note on plan selection: with a few hundred chunks Postgres legitimately prefers a
sequential scan plus sort over the HNSW index. That is the planner's correct
choice, not a misconfiguration — forcing `enable_seqscan=off` shows the index is
used. It becomes the default as the corpus grows.

### Installing pgvector on Windows

The usual route is building from source, which needs the Windows SDK (C runtime
headers) *and* administrator rights to write into `Program Files\PostgreSQL`.

If that is unavailable, a prebuilt binary for the exact major version works:

1. Download `vector.v<version>-pg18.zip` from
   [andreiramani/pgvector_pgsql_windows](https://github.com/andreiramani/pgvector_pgsql_windows/releases).
2. With an elevated shell, copy `lib\vector.dll` to `PostgreSQL\18\lib`, the
   `share\extension\*` files to `PostgreSQL\18\share\extension`, and
   `include\server\extension\vector\*` to the matching include path.
3. `CREATE EXTENSION vector;` in each database.

Verify with `SELECT extversion FROM pg_extension WHERE extname = 'vector';`.

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
