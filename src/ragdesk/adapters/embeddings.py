"""Embedding providers."""

from __future__ import annotations

import hashlib
import itertools
import math
import re
from collections.abc import Sequence

import httpx

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "our",
        "so",
        "that",
        "the",
        "their",
        "there",
        "this",
        "to",
        "was",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
    ]
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


def _stem(token: str) -> str:
    # Crude suffix stripping so "refunds" and "refund" share a feature.
    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


class HashingEmbedder:
    """Deterministic feature-hashing embedder.

    Not semantically strong, but it needs no network or model download, is
    stable across runs, and captures lexical overlap well enough for tests,
    local development and the evaluation baseline. Production uses a hosted
    model (see VoyageEmbedder).
    """

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        tokens = [_stem(t) for t in tokenize(text)]
        features = tokens + [f"{a}_{b}" for a, b in itertools.pairwise(tokens)]
        for feat in features:
            digest = hashlib.blake2b(feat.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec

    async def embed(self, texts: Sequence[str], *, kind: str) -> list[list[float]]:
        return [self._vector(t) for t in texts]


class VoyageEmbedder:
    """Voyage AI embeddings over HTTPS, batched to the provider's limit."""

    BATCH = 128

    def __init__(
        self,
        api_key: str,
        model: str = "voyage-3.5",
        dimensions: int = 1024,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.dimensions = dimensions
        self._model = model
        self._client = client or httpx.AsyncClient(
            base_url="https://api.voyageai.com/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(30.0),
        )

    async def embed(self, texts: Sequence[str], *, kind: str) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), self.BATCH):
            batch = list(texts[start : start + self.BATCH])
            resp = await self._client.post(
                "/embeddings",
                json={
                    "input": batch,
                    "model": self._model,
                    "input_type": kind,
                    "output_dimension": self.dimensions,
                },
            )
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            out.extend(d["embedding"] for d in data)
        return out
