from __future__ import annotations

import httpx

from tests.conftest import ACME_RO, ACME_RW, GLOBEX

REFUND_DOC = {
    "title": "Refund process",
    "text": "Customers can request a refund within 14 days of delivery. Agents approve refunds up to 200 euros.",
    "source_uri": "https://wiki.example.com/refunds",
}


async def test_ingest_search_answer_roundtrip(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/collections/support/documents", json=REFUND_DOC, headers=ACME_RW)
    assert r.status_code == 201, r.text
    assert r.json()["chunks"] == 1

    r = await client.post("/v1/collections/support/search", json={"query": "refund window"}, headers=ACME_RO)
    assert r.status_code == 200
    assert r.json()["hits"][0]["title"] == "Refund process"

    r = await client.post(
        "/v1/collections/support/answers",
        json={"question": "How many days do customers have to ask for a refund?"},
        headers=ACME_RO,
    )
    body = r.json()
    assert body["grounded"] is True
    assert body["citations"][0]["source_uri"] == "https://wiki.example.com/refunds"
    assert "14 days" in body["answer"]


async def test_identical_upload_is_deduplicated(client: httpx.AsyncClient) -> None:
    first = await client.post("/v1/collections/support/documents", json=REFUND_DOC, headers=ACME_RW)
    again = await client.post("/v1/collections/support/documents", json=REFUND_DOC, headers=ACME_RW)
    assert again.status_code == 200
    assert again.json() == {"document_id": first.json()["document_id"], "chunks": 0, "deduplicated": True}


async def test_tenants_are_isolated(client: httpx.AsyncClient) -> None:
    doc = (await client.post("/v1/collections/support/documents", json=REFUND_DOC, headers=ACME_RW)).json()

    r = await client.post("/v1/collections/support/search", json={"query": "refund"}, headers=GLOBEX)
    assert r.json()["hits"] == []
    r = await client.delete(f"/v1/collections/support/documents/{doc['document_id']}", headers=GLOBEX)
    assert r.status_code == 404

    r = await client.delete(f"/v1/collections/support/documents/{doc['document_id']}", headers=ACME_RW)
    assert r.status_code == 204


async def test_unanswerable_question_abstains_without_calling_the_model(client: httpx.AsyncClient) -> None:
    await client.post("/v1/collections/support/documents", json=REFUND_DOC, headers=ACME_RW)
    r = await client.post(
        "/v1/collections/support/answers",
        json={"question": "Which conference rooms have projectors?"},
        headers=ACME_RO,
    )
    body = r.json()
    assert body["grounded"] is False
    assert body["model"] == "none"
    assert body["citations"] == []


async def test_auth_and_scopes(client: httpx.AsyncClient) -> None:
    url = "/v1/collections/support/documents"
    assert (await client.post(url, json=REFUND_DOC)).status_code == 401
    bad = {"Authorization": "Bearer rdk_acmerw_wrong-secret"}
    r = await client.post(url, json=REFUND_DOC, headers=bad)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    r = await client.post(url, json=REFUND_DOC, headers=ACME_RO)
    assert r.status_code == 403
    assert r.json()["error"] == "forbidden"


async def test_validation(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/collections/Bad Name/search", json={"query": "x"}, headers=ACME_RO)
    assert r.status_code == 422
    r = await client.post("/v1/collections/support/search", json={"query": "x", "k": 99}, headers=ACME_RO)
    assert r.status_code == 422


async def test_operational_endpoints(client: httpx.AsyncClient) -> None:
    assert (await client.get("/healthz")).status_code == 200
    assert (await client.get("/readyz")).status_code == 200
    await client.post("/v1/collections/support/search", json={"query": "x"}, headers=ACME_RO)
    metrics = (await client.get("/metrics")).text
    assert 'ragdesk_http_requests_total{route="/v1/collections/{collection}/search",status="200"}' in metrics
