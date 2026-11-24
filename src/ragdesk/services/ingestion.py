from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ragdesk.domain.chunking import ChunkingPolicy, chunk_text
from ragdesk.domain.models import (
    Chunk,
    Document,
    Principal,
    Scope,
    ValidationError,
    content_hash,
    validate_collection,
)
from ragdesk.ports import DocumentStore, Embedder
from ragdesk.services.authz import require

MAX_DOCUMENT_CHARS = 2_000_000


@dataclass(frozen=True, slots=True)
class IngestResult:
    document_id: UUID
    chunks: int
    deduplicated: bool


class IngestionService:
    def __init__(
        self, store: DocumentStore, embedder: Embedder, policy: ChunkingPolicy | None = None
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._policy = policy or ChunkingPolicy()

    async def ingest(
        self, principal: Principal, collection: str, title: str, text: str, source_uri: str | None = None
    ) -> IngestResult:
        require(principal, Scope.INGEST)
        validate_collection(collection)
        if not text.strip():
            raise ValidationError("document text is empty")
        if len(text) > MAX_DOCUMENT_CHARS:
            raise ValidationError(f"document exceeds {MAX_DOCUMENT_CHARS} characters")

        digest = content_hash(text)
        # Re-uploading identical content is a no-op, which makes ingestion
        # pipelines safe to retry.
        existing = await self._store.find_by_hash(principal.tenant_id, collection, digest)
        if existing:
            return IngestResult(existing.id, 0, deduplicated=True)

        pieces = chunk_text(text, self._policy)
        # The title is embedded with each chunk so headings help retrieval.
        vectors = await self._embedder.embed([f"{title}\n{p}" for p in pieces], kind="document")
        doc = Document(principal.tenant_id, collection, title.strip(), source_uri, digest)
        chunks = [Chunk(doc.id, i, p, tuple(v)) for i, (p, v) in enumerate(zip(pieces, vectors, strict=True))]
        await self._store.add(doc, chunks)
        return IngestResult(doc.id, len(chunks), deduplicated=False)

    async def delete(self, principal: Principal, collection: str, document_id: UUID) -> bool:
        require(principal, Scope.INGEST)
        return await self._store.delete(principal.tenant_id, validate_collection(collection), document_id)
