"""Splits documents into overlapping chunks along natural boundaries.

Chunks follow paragraphs first, then sentences, so a chunk rarely cuts a
sentence in half. Size is measured in words, a stable proxy for tokens that
needs no tokenizer dependency (about 0.75 words per token for English).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


@dataclass(frozen=True, slots=True)
class ChunkingPolicy:
    max_words: int = 180
    overlap_words: int = 30

    def __post_init__(self) -> None:
        if self.max_words < 20:
            raise ValueError("max_words must be at least 20")
        if not 0 <= self.overlap_words < self.max_words // 2:
            raise ValueError("overlap_words must be between 0 and max_words / 2")


def _units(text: str) -> list[str]:
    """Paragraphs, with oversized paragraphs broken into sentences."""
    units: list[str] = []
    for para in re.split(r"\n\s*\n", text.strip()):
        para = " ".join(para.split())
        if para:
            units.extend(_SENTENCE_END.split(para))
    return units


def chunk_text(text: str, policy: ChunkingPolicy | None = None) -> list[str]:
    policy = policy or ChunkingPolicy()
    chunks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            chunks.append(" ".join(current))

    for unit in _units(text):
        words = unit.split()
        # A single sentence longer than the limit is hard-split by words.
        while len(words) > policy.max_words:
            flush()
            current = []
            chunks.append(" ".join(words[: policy.max_words]))
            words = words[policy.max_words - policy.overlap_words :]
        if len(current) + len(words) > policy.max_words:
            flush()
            current = current[-policy.overlap_words :] if policy.overlap_words else []
        current.extend(words)
    flush()
    return chunks
