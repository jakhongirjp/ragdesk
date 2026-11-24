"""Offline retrieval and abstention evaluation.

    ragdesk-eval [--k 5] [--min-recall 0.9] [--min-abstention 0.66]

Loads a corpus and a labelled question set, runs the real ingestion,
retrieval and answering services against the in-memory store, and reports:

- recall@k: the expected document appears in the top k hits
- MRR: mean reciprocal rank of the expected document
- abstention: unanswerable questions correctly answered "not found"

Exits 1 when a metric is below its threshold, so CI catches retrieval
regressions (chunking, fusion, thresholds) before they ship.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from ragdesk.adapters.embeddings import HashingEmbedder
from ragdesk.adapters.generation import ExtractiveGenerator
from ragdesk.adapters.memory import MemoryDocumentStore, MemoryQueryLog
from ragdesk.domain.models import Principal, Scope
from ragdesk.ports import Embedder
from ragdesk.services.answering import AnsweringService
from ragdesk.services.ingestion import IngestionService
from ragdesk.services.retrieval import RetrievalService, RetrievalSettings

EVAL_PRINCIPAL = Principal("eval", "eval", frozenset({Scope.ADMIN}))


@dataclass(frozen=True)
class Report:
    k: int
    recall: float
    mrr: float
    abstention: float
    answerable: int
    unanswerable: int
    misses: list[str]

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__ | {
            "recall": round(self.recall, 3),
            "mrr": round(self.mrr, 3),
            "abstention": round(self.abstention, 3),
        }


def _load(path: Path | None, name: str) -> list[dict[str, Any]]:
    text = path.read_text() if path else resources.files(__package__).joinpath("data", name).read_text()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


async def evaluate(
    corpus: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    k: int = 5,
    embedder: Embedder | None = None,
    min_similarity: float = 0.15,
) -> Report:
    embedder = embedder or HashingEmbedder()
    store = MemoryDocumentStore()
    ingestion = IngestionService(store, embedder)
    for doc in corpus:
        await ingestion.ingest(EVAL_PRINCIPAL, "eval", doc["title"], doc["text"])
    retrieval = RetrievalService(store, embedder, RetrievalSettings(min_similarity=min_similarity))
    answering = AnsweringService(retrieval, ExtractiveGenerator(), MemoryQueryLog())

    hits_at_k = 0
    rr_total = 0.0
    abstained = 0
    misses: list[str] = []
    answerable = [q for q in questions if q["expected"]]
    unanswerable = [q for q in questions if not q["expected"]]

    for q in answerable:
        hits = await retrieval.search(EVAL_PRINCIPAL, "eval", q["question"], k)
        titles = [h.title for h in hits]
        if q["expected"] in titles:
            hits_at_k += 1
            rr_total += 1 / (titles.index(q["expected"]) + 1)
        else:
            misses.append(q["question"])
    for q in unanswerable:
        result = await answering.ask(EVAL_PRINCIPAL, "eval", q["question"], k)
        if not result.answer.grounded:
            abstained += 1

    return Report(
        k=k,
        recall=hits_at_k / len(answerable) if answerable else 1.0,
        mrr=rr_total / len(answerable) if answerable else 1.0,
        abstention=abstained / len(unanswerable) if unanswerable else 1.0,
        answerable=len(answerable),
        unanswerable=len(unanswerable),
        misses=misses,
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="ragdesk-eval")
    p.add_argument("--corpus", type=Path)
    p.add_argument("--questions", type=Path)
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--min-recall", type=float, default=0.9)
    p.add_argument("--min-abstention", type=float, default=0.66)
    args = p.parse_args(argv)

    report = asyncio.run(
        evaluate(_load(args.corpus, "corpus.jsonl"), _load(args.questions, "questions.jsonl"), args.k)
    )
    print(json.dumps(report.as_dict(), indent=2))
    failed = report.recall < args.min_recall or report.abstention < args.min_abstention
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
