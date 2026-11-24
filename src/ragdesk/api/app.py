"""HTTP API. Thin: parse, authorize, call a service, shape the response."""

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ragdesk.api.metrics import ANSWERS, HTTP_LATENCY, HTTP_REQUESTS, INGESTED_CHUNKS, REGISTRY
from ragdesk.api.schemas import (
    AskRequest,
    AskResponse,
    CitationOut,
    HitOut,
    IngestRequest,
    IngestResponse,
    SearchRequest,
    SearchResponse,
)
from ragdesk.domain.models import NotFoundError, Principal, ValidationError
from ragdesk.ports import DocumentStore, KeyStore
from ragdesk.services.answering import AnsweringService
from ragdesk.services.authz import ForbiddenError
from ragdesk.services.ingestion import IngestionService
from ragdesk.services.retrieval import RetrievalService

log = logging.getLogger("ragdesk")


@dataclass
class Container:
    """Everything the routes need, built once at startup."""

    store: DocumentStore
    keys: KeyStore
    ingestion: IngestionService
    retrieval: RetrievalService
    answering: AnsweringService
    close: Callable[[], Awaitable[None]] | None = None


class Unauthorized(Exception):
    pass


def create_app(build: Callable[[], Awaitable[Container]]) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = await build()
        yield
        if app.state.container.close:
            await app.state.container.close()

    app = FastAPI(title="ragdesk", version="0.1.0", lifespan=lifespan)

    def container(request: Request) -> Container:
        c: Container = request.app.state.container
        return c

    async def principal(request: Request, authorization: Annotated[str | None, Header()] = None) -> Principal:
        if not authorization or not authorization.startswith("Bearer "):
            raise Unauthorized
        p = await container(request).keys.resolve(authorization.removeprefix("Bearer ").strip())
        if p is None:
            raise Unauthorized
        return p

    Auth = Annotated[Principal, Depends(principal)]
    Deps = Annotated[Container, Depends(container)]

    def problem(status: int, error: str, message: str) -> JSONResponse:
        return JSONResponse({"error": error, "message": message}, status_code=status)

    @app.exception_handler(Unauthorized)
    async def _unauthorized(_: Request, __: Unauthorized) -> JSONResponse:
        resp = problem(401, "unauthorized", "a valid API key is required")
        resp.headers["WWW-Authenticate"] = "Bearer"
        return resp

    @app.exception_handler(ForbiddenError)
    async def _forbidden(_: Request, exc: ForbiddenError) -> JSONResponse:
        return problem(403, "forbidden", str(exc))

    @app.exception_handler(ValidationError)
    async def _invalid(_: Request, exc: ValidationError) -> JSONResponse:
        return problem(422, "validation_failed", str(exc))

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return problem(404, "not_found", str(exc))

    @app.middleware("http")
    async def observe(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        HTTP_REQUESTS.labels(path, str(response.status_code)).inc()
        HTTP_LATENCY.labels(path).observe(time.perf_counter() - started)
        return response

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz(c: Deps) -> dict[str, str]:
        await c.store.ping()
        return {"status": "ready"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/collections/{collection}/documents", status_code=201, response_model=IngestResponse)
    async def ingest(
        collection: str, body: IngestRequest, p: Auth, c: Deps, response: Response
    ) -> IngestResponse:
        r = await c.ingestion.ingest(
            p, collection, body.title, body.text, str(body.source_uri) if body.source_uri else None
        )
        INGESTED_CHUNKS.inc(r.chunks)
        if r.deduplicated:
            response.status_code = 200
        return IngestResponse(document_id=r.document_id, chunks=r.chunks, deduplicated=r.deduplicated)

    @app.delete("/v1/collections/{collection}/documents/{document_id}", status_code=204)
    async def delete(collection: str, document_id: UUID, p: Auth, c: Deps) -> Response:
        if not await c.ingestion.delete(p, collection, document_id):
            raise NotFoundError("document not found")
        return Response(status_code=204)

    @app.post("/v1/collections/{collection}/search", response_model=SearchResponse)
    async def search(collection: str, body: SearchRequest, p: Auth, c: Deps) -> SearchResponse:
        hits = await c.retrieval.search(p, collection, body.query, body.k)
        return SearchResponse(
            hits=[
                HitOut(
                    chunk_id=h.chunk_id,
                    document_id=h.document_id,
                    title=h.title,
                    source_uri=h.source_uri,
                    text=h.text,
                    score=round(h.score, 6),
                )
                for h in hits
            ]
        )

    @app.post("/v1/collections/{collection}/answers", response_model=AskResponse)
    async def ask(collection: str, body: AskRequest, p: Auth, c: Deps) -> AskResponse:
        r = await c.answering.ask(p, collection, body.question, body.k)
        ANSWERS.labels(str(r.answer.grounded).lower()).inc()
        return AskResponse(
            answer=r.answer.text,
            grounded=r.answer.grounded,
            citations=[
                CitationOut(
                    index=ci.index,
                    document_id=ci.document_id,
                    title=ci.title,
                    source_uri=ci.source_uri,
                    snippet=ci.snippet,
                )
                for ci in r.answer.citations
            ],
            model=r.answer.model,
            latency_ms=r.latency_ms,
        )

    return app
