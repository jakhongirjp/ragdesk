"""Domain entities. Plain dataclasses with no framework or storage imports."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

COLLECTION_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


class Scope(StrEnum):
    READ = "read"
    INGEST = "ingest"
    ADMIN = "admin"


class DomainError(Exception):
    """Base class for errors the API maps to client-facing responses."""


class ValidationError(DomainError):
    pass


class NotFoundError(DomainError):
    pass


def validate_collection(name: str) -> str:
    if not COLLECTION_RE.match(name):
        raise ValidationError("collection must be 1-63 chars of a-z, 0-9, '-' or '_'")
    return name


def content_hash(text: str) -> str:
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Document:
    tenant_id: str
    collection: str
    title: str
    source_uri: str | None
    content_hash: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True, slots=True)
class Chunk:
    document_id: UUID
    ordinal: int
    text: str
    embedding: tuple[float, ...]
    id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, slots=True)
class Hit:
    """A retrieved chunk with the document metadata needed to cite it."""

    chunk_id: UUID
    document_id: UUID
    title: str
    source_uri: str | None
    text: str
    score: float
    similarity: float


@dataclass(frozen=True, slots=True)
class Citation:
    index: int
    document_id: UUID
    chunk_id: UUID
    title: str
    source_uri: str | None
    snippet: str


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    grounded: bool
    citations: tuple[Citation, ...]
    model: str


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller, resolved from an API key."""

    key_id: str
    tenant_id: str
    scopes: frozenset[Scope]

    def can(self, scope: Scope) -> bool:
        return scope in self.scopes or Scope.ADMIN in self.scopes
