"""Integration tests against PostgreSQL with pgvector.

Skipped unless RAGDESK_TEST_DATABASE_URL points at a server where the user
may create databases.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from ragdesk.adapters.embeddings import HashingEmbedder
from ragdesk.adapters.postgres import PostgresDocumentStore, PostgresKeyStore, create_pool, migrate
from ragdesk.domain.models import Principal, Scope
from ragdesk.services.ingestion import IngestionService
from ragdesk.services.retrieval import RetrievalService

ADMIN_URL = os.environ.get("RAGDESK_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="RAGDESK_TEST_DATABASE_URL not set")


@pytest.fixture
async def pool() -> AsyncIterator[AsyncConnectionPool]:
    assert ADMIN_URL
    name = f"ragdesk_test_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {name}")
    url = psycopg.conninfo.make_conninfo(ADMIN_URL, dbname=name)
    p = await create_pool(url, max_size=4)
    await migrate(p, 384)
    yield p
    await p.close()
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


ACME = Principal("k1", "acme", frozenset({Scope.READ, Scope.INGEST}))
GLOBEX = Principal("k2", "globex", frozenset({Scope.READ, Scope.INGEST}))


async def test_hybrid_search_and_isolation(pool: AsyncConnectionPool) -> None:
    store, emb = PostgresDocumentStore(pool), HashingEmbedder()
    ingest, retrieval = IngestionService(store, emb), RetrievalService(store, emb)
    await ingest.ingest(
        ACME, "hr", "Annual leave", "Employees receive 28 days of paid annual leave per year."
    )
    await ingest.ingest(
        ACME, "hr", "Expenses", "Meals are reimbursed up to 45 euros per day while travelling."
    )
    await ingest.ingest(GLOBEX, "hr", "Annual leave", "Globex staff receive 20 days of leave.")

    hits = await retrieval.search(ACME, "hr", "how many vacation days of annual leave", 3)
    assert hits[0].title == "Annual leave"
    assert "28 days" in hits[0].text
    assert all("Globex" not in h.text for h in hits)

    keyword = await store.keyword_search("acme", "hr", "reimbursed meals", 5)
    assert [h.title for h in keyword] == ["Expenses"]


async def test_dedup_delete_and_migration_idempotency(pool: AsyncConnectionPool) -> None:
    store = PostgresDocumentStore(pool)
    ingest = IngestionService(store, HashingEmbedder())
    first = await ingest.ingest(ACME, "hr", "Doc", "Some text here.")
    again = await ingest.ingest(ACME, "hr", "Doc", "Some   text here.")
    assert again.deduplicated and again.document_id == first.document_id
    assert not await ingest.delete(GLOBEX, "hr", first.document_id)
    assert await ingest.delete(ACME, "hr", first.document_id)
    await migrate(pool, 384)  # second run is a no-op


async def test_api_keys(pool: AsyncConnectionPool) -> None:
    keys = PostgresKeyStore(pool)
    raw = await keys.create("acme", "ci", frozenset({Scope.READ}))
    p = await keys.resolve(raw)
    assert p and p.tenant_id == "acme" and p.scopes == frozenset({Scope.READ})
    assert await keys.resolve(raw[:-1] + "x") is None
    assert await keys.revoke(p.key_id)
    assert await keys.resolve(raw) is None
