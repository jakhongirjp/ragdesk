# 0001. Store vectors in Postgres with pgvector

Status: accepted

## Context

Ragdesk needs approximate nearest-neighbour search over chunk embeddings, plus
documents, API keys and an audit log. A dedicated vector database (Pinecone,
Qdrant, Weaviate) is the common choice.

## Decision

Use Postgres with the pgvector extension and an HNSW index on cosine distance.
Documents, chunks, keys and the query log share one database.

## Consequences

- Deleting a document removes its vectors in the same transaction (`ON DELETE CASCADE`).
  With a separate vector store, deletes are eventually consistent and a source of
  "deleted policy still quoted" incidents.
- Tenant filters, backups, point-in-time recovery and access control are the ones
  the team already runs for Postgres.
- Keyword search (`tsvector`) sits next to the vectors, which makes hybrid retrieval
  a single round trip per ranking (ADR 0002).
- HNSW in pgvector is comfortable into the low tens of millions of chunks per
  instance. Beyond that, partition `chunks` by tenant or move the dense index out.
  The `DocumentStore` port keeps that change local to one adapter.
- Embedding dimension is fixed at the first migration. Changing embedding models
  means a re-embed job into a new column, not an in-place change.
