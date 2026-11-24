"""Interfaces the services depend on. Adapters implement them."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from ragdesk.domain.models import Answer, Chunk, Document, Hit, Principal


class Embedder(Protocol):
    dimensions: int

    async def embed(self, texts: Sequence[str], *, kind: str) -> list[list[float]]:
        """kind is "document" or "query"; some providers embed them differently."""
        ...


class Generator(Protocol):
    async def answer(self, question: str, hits: Sequence[Hit]) -> Answer: ...


class DocumentStore(Protocol):
    async def find_by_hash(self, tenant_id: str, collection: str, content_hash: str) -> Document | None: ...

    async def add(self, document: Document, chunks: Sequence[Chunk]) -> None: ...

    async def delete(self, tenant_id: str, collection: str, document_id: UUID) -> bool: ...

    async def vector_search(
        self, tenant_id: str, collection: str, embedding: Sequence[float], limit: int
    ) -> list[Hit]: ...

    async def keyword_search(self, tenant_id: str, collection: str, query: str, limit: int) -> list[Hit]: ...

    async def ping(self) -> None: ...


class KeyStore(Protocol):
    async def resolve(self, raw_key: str) -> Principal | None: ...


class QueryLog(Protocol):
    async def record(
        self,
        principal: Principal,
        collection: str,
        question: str,
        chunk_ids: Sequence[UUID],
        grounded: bool,
        latency_ms: int,
    ) -> None: ...
