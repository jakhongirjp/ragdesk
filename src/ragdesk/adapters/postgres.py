"""PostgreSQL + pgvector adapters.

Every query filters on (tenant_id, collection) first; tenancy is enforced in
SQL, not by callers remembering to check.
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Sequence
from importlib import resources
from uuid import UUID

import numpy as np
from pgvector.psycopg import register_vector_async
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from ragdesk.adapters.memory import hash_secret
from ragdesk.domain.models import Chunk, Document, Hit, Principal, Scope

_MIGRATION_LOCK = 4_711_001


async def _configure(conn: AsyncConnection) -> None:
    await register_vector_async(conn)


async def create_pool(url: str, min_size: int = 1, max_size: int = 10) -> AsyncConnectionPool:
    # Install the extension before registering the vector type on pooled connections.
    async with await AsyncConnection.connect(url, autocommit=True) as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    pool = AsyncConnectionPool(url, min_size=min_size, max_size=max_size, configure=_configure, open=False)
    await pool.open()
    return pool


async def migrate(pool: AsyncConnectionPool, dimensions: int) -> None:
    files = sorted(
        (f for f in resources.files("ragdesk").joinpath("migrations").iterdir() if f.name.endswith(".sql")),
        key=lambda f: f.name,
    )
    async with pool.connection() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK,))
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, "
            "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        for f in files:
            cur = await conn.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (f.name,))
            if await cur.fetchone():
                continue
            sql = f.read_text().replace("{dimensions}", str(int(dimensions)))
            await conn.execute(sql.encode())
            await conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (f.name,))


_HIT_COLUMNS = "c.id, c.document_id, d.title, d.source_uri, c.text"


class PostgresDocumentStore:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def find_by_hash(self, tenant_id: str, collection: str, content_hash: str) -> Document | None:
        async with self._pool.connection() as conn:
            cur = conn.cursor(row_factory=dict_row)
            await cur.execute(
                "SELECT * FROM documents WHERE tenant_id=%s AND collection=%s AND content_hash=%s",
                (tenant_id, collection, content_hash),
            )
            row = await cur.fetchone()
        return Document(**row) if row else None

    async def add(self, document: Document, chunks: Sequence[Chunk]) -> None:
        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO documents (id, tenant_id, collection, title, source_uri, content_hash, created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    document.id,
                    document.tenant_id,
                    document.collection,
                    document.title,
                    document.source_uri,
                    document.content_hash,
                    document.created_at,
                ),
            )
            async with conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO chunks (id, document_id, tenant_id, collection, ordinal, text, embedding) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    [
                        (
                            c.id,
                            document.id,
                            document.tenant_id,
                            document.collection,
                            c.ordinal,
                            c.text,
                            np.asarray(c.embedding, dtype=np.float32),
                        )
                        for c in chunks
                    ],
                )

    async def delete(self, tenant_id: str, collection: str, document_id: UUID) -> bool:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "DELETE FROM documents WHERE id=%s AND tenant_id=%s AND collection=%s",
                (document_id, tenant_id, collection),
            )
            return cur.rowcount == 1

    async def vector_search(
        self, tenant_id: str, collection: str, embedding: Sequence[float], limit: int
    ) -> list[Hit]:
        vec = np.asarray(embedding, dtype=np.float32)
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                f"SELECT {_HIT_COLUMNS}, 1 - (c.embedding <=> %s) AS sim "  # noqa: S608 - constant columns
                "FROM chunks c JOIN documents d ON d.id = c.document_id "
                "WHERE c.tenant_id=%s AND c.collection=%s ORDER BY c.embedding <=> %s LIMIT %s",
                (vec, tenant_id, collection, vec, limit),
            )
            rows = await cur.fetchall()
        return [Hit(r[0], r[1], r[2], r[3], r[4], float(r[5]), float(r[5])) for r in rows]

    async def keyword_search(self, tenant_id: str, collection: str, query: str, limit: int) -> list[Hit]:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                f"SELECT {_HIT_COLUMNS}, ts_rank_cd(c.tsv, q) AS rank "  # noqa: S608 - constant columns
                "FROM chunks c JOIN documents d ON d.id = c.document_id, "
                "websearch_to_tsquery('english', %s) q "
                "WHERE c.tenant_id=%s AND c.collection=%s AND c.tsv @@ q ORDER BY rank DESC LIMIT %s",
                (query, tenant_id, collection, limit),
            )
            rows = await cur.fetchall()
        return [Hit(r[0], r[1], r[2], r[3], r[4], float(r[5]), 0.0) for r in rows]

    async def ping(self) -> None:
        async with self._pool.connection() as conn:
            await conn.execute("SELECT 1")


class PostgresKeyStore:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def create(self, tenant_id: str, name: str, scopes: frozenset[Scope]) -> str:
        key_id, secret = secrets.token_hex(6), secrets.token_urlsafe(32)
        async with self._pool.connection() as conn:
            await conn.execute(
                "INSERT INTO api_keys (id, tenant_id, name, secret_hash, scopes) VALUES (%s,%s,%s,%s,%s)",
                (key_id, tenant_id, name, hash_secret(secret), sorted(s.value for s in scopes)),
            )
        return f"rdk_{key_id}_{secret}"

    async def resolve(self, raw_key: str) -> Principal | None:
        parts = raw_key.split("_", 2)
        if len(parts) != 3 or parts[0] != "rdk":
            return None
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT tenant_id, secret_hash, scopes FROM api_keys WHERE id=%s AND revoked_at IS NULL",
                (parts[1],),
            )
            row = await cur.fetchone()
        if row is None or not hmac.compare_digest(row[1], hash_secret(parts[2])):
            return None
        return Principal(key_id=parts[1], tenant_id=row[0], scopes=frozenset(Scope(s) for s in row[2]))

    async def revoke(self, key_id: str) -> bool:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "UPDATE api_keys SET revoked_at=now() WHERE id=%s AND revoked_at IS NULL", (key_id,)
            )
            return cur.rowcount == 1


class PostgresQueryLog:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def record(
        self,
        principal: Principal,
        collection: str,
        question: str,
        chunk_ids: Sequence[UUID],
        grounded: bool,
        latency_ms: int,
    ) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "INSERT INTO query_log (tenant_id, key_id, collection, question, chunk_ids, grounded, latency_ms) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    principal.tenant_id,
                    principal.key_id,
                    collection,
                    question,
                    list(chunk_ids),
                    grounded,
                    latency_ms,
                ),
            )
