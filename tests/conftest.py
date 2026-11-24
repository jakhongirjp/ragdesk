from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from ragdesk.api.app import create_app
from ragdesk.bootstrap import build_container
from ragdesk.config import Settings

KEYS = [
    "acme:read,ingest:acmerw:s3cret-acme-rw",
    "acme:read:acmero:s3cret-acme-ro",
    "globex:read,ingest:globexrw:s3cret-globex",
]


def bearer(key_id: str, secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer rdk_{key_id}_{secret}"}


ACME_RW = bearer("acmerw", "s3cret-acme-rw")
ACME_RO = bearer("acmero", "s3cret-acme-ro")
GLOBEX = bearer("globexrw", "s3cret-globex")


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(store="memory", bootstrap_keys=KEYS)
    app = create_app(lambda: build_container(settings))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
