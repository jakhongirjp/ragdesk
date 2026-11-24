from __future__ import annotations

import time
from dataclasses import dataclass

from ragdesk.adapters.generation import NO_ANSWER
from ragdesk.domain.models import Answer, Hit, Principal
from ragdesk.ports import Generator, QueryLog
from ragdesk.services.retrieval import RetrievalService


@dataclass(frozen=True, slots=True)
class AnswerResult:
    answer: Answer
    hits: list[Hit]
    latency_ms: int


class AnsweringService:
    def __init__(self, retrieval: RetrievalService, generator: Generator, log: QueryLog) -> None:
        self._retrieval = retrieval
        self._generator = generator
        self._log = log

    async def ask(self, principal: Principal, collection: str, question: str, k: int = 5) -> AnswerResult:
        started = time.perf_counter()
        hits = await self._retrieval.search(principal, collection, question, k)
        if self._retrieval.is_relevant(hits):
            answer = await self._generator.answer(question, hits)
        else:
            # Skip the model call entirely: cheaper, and nothing to hallucinate from.
            answer = Answer(NO_ANSWER, grounded=False, citations=(), model="none")
        latency_ms = int((time.perf_counter() - started) * 1000)
        await self._log.record(
            principal, collection, question, [h.chunk_id for h in hits], answer.grounded, latency_ms
        )
        return AnswerResult(answer, hits, latency_ms)
