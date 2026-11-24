from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class IngestRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1)
    source_uri: HttpUrl | None = None


class IngestResponse(BaseModel):
    document_id: UUID
    chunks: int
    deduplicated: bool


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    k: int = Field(5, ge=1, le=20)


class HitOut(BaseModel):
    chunk_id: UUID
    document_id: UUID
    title: str
    source_uri: str | None
    text: str
    score: float


class SearchResponse(BaseModel):
    hits: list[HitOut]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    k: int = Field(5, ge=1, le=20)


class CitationOut(BaseModel):
    index: int
    document_id: UUID
    title: str
    source_uri: str | None
    snippet: str


class AskResponse(BaseModel):
    answer: str
    grounded: bool
    citations: list[CitationOut]
    model: str
    latency_ms: int


class Problem(BaseModel):
    error: str
    message: str
