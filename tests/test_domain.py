from __future__ import annotations

from uuid import uuid4

import pytest

from ragdesk.adapters.embeddings import HashingEmbedder
from ragdesk.domain.chunking import ChunkingPolicy, chunk_text
from ragdesk.domain.models import Hit, ValidationError, content_hash, validate_collection
from ragdesk.services.retrieval import reciprocal_rank_fusion


def words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


class TestChunking:
    def test_short_text_is_one_chunk(self) -> None:
        assert chunk_text("One paragraph.\n\nAnother one.") == ["One paragraph. Another one."]

    def test_respects_max_words_and_overlap(self) -> None:
        policy = ChunkingPolicy(max_words=50, overlap_words=10)
        text = "\n\n".join(f"{words(20, f'p{i}_')}." for i in range(6))
        chunks = chunk_text(text, policy)
        assert len(chunks) > 1
        assert all(len(c.split()) <= 50 for c in chunks)
        # The tail of one chunk is repeated at the head of the next.
        assert chunks[0].split()[-10:] == chunks[1].split()[:10]

    def test_hard_splits_a_giant_sentence(self) -> None:
        chunks = chunk_text(words(130), ChunkingPolicy(max_words=50, overlap_words=5))
        assert all(len(c.split()) <= 50 for c in chunks)
        assert chunks[-1].split()[-1] == "w129"

    @pytest.mark.parametrize("bad", [dict(max_words=10), dict(max_words=50, overlap_words=30)])
    def test_rejects_bad_policy(self, bad: dict[str, int]) -> None:
        with pytest.raises(ValueError):
            ChunkingPolicy(**bad)


def test_collection_names() -> None:
    assert validate_collection("hr-policies") == "hr-policies"
    for bad in ["", "Has Caps", "../etc", "x" * 64]:
        with pytest.raises(ValidationError):
            validate_collection(bad)


def test_content_hash_ignores_whitespace() -> None:
    assert content_hash("a  b\n c") == content_hash("a b c")
    assert content_hash("a b") != content_hash("a c")


async def test_hashing_embedder_is_deterministic_and_normalized() -> None:
    e = HashingEmbedder(64)
    [a], [b] = await e.embed(["Refund policy"], kind="query"), await e.embed(["Refund policy"], kind="query")
    assert a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-9
    [empty] = await e.embed(["the and of"], kind="query")  # stopwords only
    assert not any(empty)


def _hit(sim: float = 0.0) -> Hit:
    return Hit(uuid4(), uuid4(), "t", None, "text", 0.0, sim)


def test_rrf_rewards_agreement_between_rankings() -> None:
    a, b, c = _hit(0.9), _hit(0.5), _hit()
    fused = reciprocal_rank_fusion([[a, b], [b, c]])
    assert [h.chunk_id for h in fused] == [b.chunk_id, a.chunk_id, c.chunk_id]
    assert fused[0].similarity == 0.5  # keeps the vector similarity
