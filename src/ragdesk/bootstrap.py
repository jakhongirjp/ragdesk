"""Composition root: turns Settings into a wired Container."""

from __future__ import annotations

import anthropic

from ragdesk.adapters.embeddings import HashingEmbedder, VoyageEmbedder
from ragdesk.adapters.generation import ClaudeGenerator, ExtractiveGenerator
from ragdesk.adapters.memory import MemoryDocumentStore, MemoryKeyStore, MemoryQueryLog
from ragdesk.api.app import Container
from ragdesk.config import Settings
from ragdesk.domain.models import Scope
from ragdesk.ports import DocumentStore, Embedder, Generator, KeyStore, QueryLog
from ragdesk.services.answering import AnsweringService
from ragdesk.services.ingestion import IngestionService
from ragdesk.services.retrieval import RetrievalService, RetrievalSettings


def build_embedder(s: Settings) -> Embedder:
    if s.embedder == "voyage":
        assert s.voyage_api_key is not None
        return VoyageEmbedder(s.voyage_api_key.get_secret_value(), s.voyage_model, s.embedding_dimensions)
    return HashingEmbedder(s.embedding_dimensions)


def build_generator(s: Settings) -> Generator:
    if s.generator == "claude":
        # Credentials resolve from the environment (ANTHROPIC_API_KEY or a profile).
        return ClaudeGenerator(anthropic.AsyncAnthropic(), s.claude_model, s.claude_effort)
    return ExtractiveGenerator()


def memory_keys(entries: list[str]) -> MemoryKeyStore:
    keys = MemoryKeyStore()
    for entry in entries:
        tenant, scopes, key_id, secret = entry.split(":", 3)
        keys.add(key_id, secret, tenant, frozenset(Scope(x) for x in scopes.split(",")))
    return keys


async def build_container(s: Settings) -> Container:
    embedder = build_embedder(s)
    store: DocumentStore
    keys: KeyStore
    log: QueryLog
    close = None
    if s.store == "postgres":
        from ragdesk.adapters.postgres import (
            PostgresDocumentStore,
            PostgresKeyStore,
            PostgresQueryLog,
            create_pool,
            migrate,
        )

        assert s.database_url is not None
        pool = await create_pool(s.database_url)
        await migrate(pool, s.embedding_dimensions)
        store, keys, log = PostgresDocumentStore(pool), PostgresKeyStore(pool), PostgresQueryLog(pool)
        close = pool.close
    else:
        store, keys, log = MemoryDocumentStore(), memory_keys(s.bootstrap_keys), MemoryQueryLog()

    retrieval = RetrievalService(store, embedder, RetrievalSettings(s.retrieval_candidates, s.min_similarity))
    return Container(
        store=store,
        keys=keys,
        ingestion=IngestionService(store, embedder),
        retrieval=retrieval,
        answering=AnsweringService(retrieval, build_generator(s), log),
        close=close,
    )
