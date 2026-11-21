-- ===========================================================================
-- First-start database initialisation (Sprint 3)
--
-- The application's `init_schema()` only *detects* pgvector: it adds the
-- `embedding_vec` column and the HNSW index inside a block guarded by
-- `IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')`. It never
-- creates the extension itself, because doing so needs superuser rights that a
-- least-privileged application role should not have.
--
-- So the extension must exist before the backend starts. This file runs once,
-- on the first initialisation of an empty `pgdata` volume, as the image's
-- superuser (`POSTGRES_USER`).
--
-- It is intentionally idempotent: `IF NOT EXISTS` makes a manual re-run safe.
-- ===========================================================================

CREATE EXTENSION IF NOT EXISTS vector;
