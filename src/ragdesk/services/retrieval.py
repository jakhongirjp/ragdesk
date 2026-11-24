"""Hybrid retrieval: dense vectors and keyword search, fused with RRF.

Dense retrieval handles paraphrase; keyword search handles exact terms that
embeddings blur (product codes, error messages, names). Reciprocal Rank
Fusion combines the two rankings without having to calibrate their scores
against each other.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, replace
from uuid import UUID

from ragdesk.domain.models import Hit, Principal, Scope, ValidationError, validate_collection
from ragdesk.ports import DocumentStore, Embedder
from ragdesk.services.authz import require

RRF_K = 60


def reciprocal_rank_fusion(rankings: Sequence[Sequence[Hit]], k: int = RRF_K) -> list[Hit]:
    scores: dict[UUID, float] = {}
    best: dict[UUID, Hit] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank)
            prev = best.get(hit.chunk_id)
            # Keep the copy that carries the vector similarity.
            if prev is None or hit.similarity > prev.similarity:
                best[hit.chunk_id] = hit
    ordered = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    return [replace(best[cid], score=scores[cid]) for cid in ordered]


@dataclass(frozen=True, slots=True)
class RetrievalSettings:
    candidates: int = 20
    min_similarity: float = 0.15


class RetrievalService:
    def __init__(self, store: DocumentStore, embedder: Embedder, settings: RetrievalSettings | None = None):
        self._store = store
        self._embedder = embedder
        self._settings = settings or RetrievalSettings()

    async def search(self, principal: Principal, collection: str, query: str, k: int) -> list[Hit]:
        require(principal, Scope.READ)
        validate_collection(collection)
        query = query.strip()
        if not query or len(query) > 2000:
            raise ValidationError("query must be 1-2000 characters")
        if not 1 <= k <= 20:
            raise ValidationError("k must be between 1 and 20")

        [vector] = await self._embedder.embed([query], kind="query")
        n = self._settings.candidates
        dense, sparse = await asyncio.gather(
            self._store.vector_search(principal.tenant_id, collection, vector, n),
            self._store.keyword_search(principal.tenant_id, collection, query, n),
        )
        fused = reciprocal_rank_fusion([dense, sparse])
        return fused[:k]

    def is_relevant(self, hits: Sequence[Hit]) -> bool:
        """Refuse to answer when nothing retrieved is close enough to the question."""
        return any(h.similarity >= self._settings.min_similarity for h in hits)
