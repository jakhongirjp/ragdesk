-- {dimensions} is substituted at migration time from RAGDESK_EMBEDDING_DIMENSIONS.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    id           UUID PRIMARY KEY,
    tenant_id    TEXT        NOT NULL,
    collection   TEXT        NOT NULL,
    title        TEXT        NOT NULL,
    source_uri   TEXT,
    content_hash TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, collection, content_hash)
);

CREATE TABLE chunks (
    id          UUID PRIMARY KEY,
    document_id UUID    NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id   TEXT    NOT NULL,
    collection  TEXT    NOT NULL,
    ordinal     INT     NOT NULL,
    text        TEXT    NOT NULL,
    embedding   vector({dimensions}) NOT NULL,
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    UNIQUE (document_id, ordinal)
);

-- Approximate nearest neighbour search on cosine distance.
CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_tsv_gin ON chunks USING gin (tsv);
CREATE INDEX chunks_scope_idx ON chunks (tenant_id, collection);

CREATE TABLE api_keys (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT        NOT NULL,
    name        TEXT        NOT NULL,
    secret_hash TEXT        NOT NULL,
    scopes      TEXT[]      NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at  TIMESTAMPTZ
);

-- Every question asked, for audit and for building evaluation sets.
CREATE TABLE query_log (
    id         BIGSERIAL PRIMARY KEY,
    tenant_id  TEXT        NOT NULL,
    key_id     TEXT        NOT NULL,
    collection TEXT        NOT NULL,
    question   TEXT        NOT NULL,
    chunk_ids  UUID[]      NOT NULL,
    grounded   BOOLEAN     NOT NULL,
    latency_ms INT         NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX query_log_tenant_idx ON query_log (tenant_id, created_at DESC);
