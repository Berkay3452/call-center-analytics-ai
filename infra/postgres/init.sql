-- Yerel Postgres ilk açılışta çalışır. Supabase'te bu eklentiler panelden/migration ile açılır.
CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector (RAG embedding'leri)
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
