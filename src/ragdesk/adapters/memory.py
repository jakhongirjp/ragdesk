"""In-memory adapters for tests and local development."""

from __future__ import annotations

import hashlib
import hmac
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from ragdesk.adapters.embeddings import _stem, tokenize
from ragdesk.domain.models import Chunk, Document, Hit, Principal, Scope


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class MemoryDocumentStore:
    def __init__(self) -> None:
        self._docs: dict[UUID, Document] = {}
        self._chunks: dict[UUID, list[Chunk]] = {}

    async def find_by_hash(self, tenant_id: str, collection: str, content_hash: str) -> Document | None:
        return next(
            (
                d
                for d in self._docs.values()
                if (d.tenant_id, d.collection, d.content_hash) == (tenant_id, collection, content_hash)
            ),
            None,
        )

    async def add(self, document: Document, chunks: Sequence[Chunk]) -> None:
        self._docs[document.id] = document
        self._chunks[document.id] = list(chunks)

    async def delete(self, tenant_id: str, collection: str, document_id: UUID) -> bool:
        doc = self._docs.get(document_id)
        if not doc or (doc.tenant_id, doc.collection) != (tenant_id, collection):
            return False
        del self._docs[document_id]
        del self._chunks[document_id]
        return True

    def _scoped(self, tenant_id: str, collection: str) -> list[tuple[Document, Chunk]]:
        return [
            (d, c)
            for d in self._docs.values()
            if d.tenant_id == tenant_id and d.collection == collection
            for c in self._chunks[d.id]
        ]

    @staticmethod
    def _hit(d: Document, c: Chunk, score: float, similarity: float) -> Hit:
        return Hit(c.id, d.id, d.title, d.source_uri, c.text, score, similarity)

    async def vector_search(
        self, tenant_id: str, collection: str, embedding: Sequence[float], limit: int
    ) -> list[Hit]:
        scored = [(d, c, _cosine(embedding, c.embedding)) for d, c in self._scoped(tenant_id, collection)]
        scored.sort(key=lambda t: t[2], reverse=True)
        return [self._hit(d, c, s, s) for d, c, s in scored[:limit]]

    async def keyword_search(self, tenant_id: str, collection: str, query: str, limit: int) -> list[Hit]:
        """BM25 over the tenant's chunks; mirrors Postgres full-text ranking closely enough."""
        pairs = self._scoped(tenant_id, collection)
        if not pairs:
            return []
        docs = [[_stem(t) for t in tokenize(c.text)] for _, c in pairs]
        avg_len = sum(map(len, docs)) / len(docs)
        df: Counter[str] = Counter(t for d in docs for t in set(d))
        terms = {_stem(t) for t in tokenize(query)}
        k1, b = 1.2, 0.75
        scored = []
        for (d, c), toks in zip(pairs, docs, strict=True):
            tf = Counter(toks)
            score = 0.0
            for t in terms:
                if t not in tf:
                    continue
                idf = math.log(1 + (len(docs) - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(toks) / avg_len))
            if score > 0:
                scored.append((d, c, score))
        scored.sort(key=lambda t: t[2], reverse=True)
        return [self._hit(d, c, s, 0.0) for d, c, s in scored[:limit]]

    async def ping(self) -> None:
        return None


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


@dataclass
class MemoryKeyStore:
    """Keys look like rdk_<key_id>_<secret>; only the secret's hash is kept."""

    _keys: dict[str, tuple[str, str, frozenset[Scope]]] = field(default_factory=dict)

    def add(self, key_id: str, secret: str, tenant_id: str, scopes: frozenset[Scope]) -> str:
        self._keys[key_id] = (hash_secret(secret), tenant_id, scopes)
        return f"rdk_{key_id}_{secret}"

    async def resolve(self, raw_key: str) -> Principal | None:
        parts = raw_key.split("_", 2)
        if len(parts) != 3 or parts[0] != "rdk":
            return None
        entry = self._keys.get(parts[1])
        if entry is None or not hmac.compare_digest(entry[0], hash_secret(parts[2])):
            return None
        return Principal(key_id=parts[1], tenant_id=entry[1], scopes=entry[2])


@dataclass
class MemoryQueryLog:
    entries: list[dict[str, object]] = field(default_factory=list)

    async def record(
        self,
        principal: Principal,
        collection: str,
        question: str,
        chunk_ids: Sequence[UUID],
        grounded: bool,
        latency_ms: int,
    ) -> None:
        self.entries.append(
            {
                "tenant_id": principal.tenant_id,
                "key_id": principal.key_id,
                "collection": collection,
                "question": question,
                "chunk_ids": list(chunk_ids),
                "grounded": grounded,
                "latency_ms": latency_ms,
            }
        )
