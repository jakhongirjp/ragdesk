# Engineering design

Architecture, data model and API are in the [README](../README.md);
decisions in the [ADRs](adr).

## Boundaries

ragdesk is one service with a ports-and-adapters core. If ingestion volume
grows, the first split is an ingestion worker consuming a queue; the
`IngestionService` already depends only on ports, so it moves without changes.

| Layer | Knows about |
|---|---|
| `domain` | Nothing outside itself |
| `services` | `domain`, `ports` |
| `adapters` | Postgres, Voyage, Anthropic SDKs |
| `api` | `services`, schemas, metrics |
| `bootstrap` | Everything; the only place adapters are chosen |

## Authentication and authorisation

- API keys `rdk_<id>_<secret>`. The id is a lookup key; only `sha256(secret)` is
  stored, compared with `hmac.compare_digest`.
- Scopes: `read` (search, answers), `ingest` (add and delete documents),
  `admin` (reserved for key management over the API, M4).
- Scope checks live in the services (`require(principal, Scope.X)`), so no
  route can skip them.
- Keys are created and revoked with `ragdesk-admin`. Planned: expiry and
  last-used timestamps (M4).

## Audit logging

`query_log` stores tenant, key id, collection, question, the chunk ids given to
the generator, whether the answer was grounded, and latency. It stores no answer
text, so a deleted document doesn't linger in the log. Ingest and delete are
not yet audited; an `ingest_log` table written in the same transaction is planned (M4).

## Security design

| Threat | Mitigation |
|---|---|
| Cross-tenant leakage | Tenant from the key, filter in every query, tests on both stores |
| Prompt injection in documents | Passages in `<document>` tags with escaped titles; system prompt treats them as data; no tools given to the model |
| Hallucinated citations | Citation indices mapped server-side to the passages actually sent |
| Key leakage | Hash-only storage, revocation, secrets never logged |
| Abuse and cost | Bounded input sizes; rate limits per key planned (M4) |
| Provider outage | Extractive generator fallback by configuration; Claude server-side fallbacks enabled |

## Performance and scaling

- Search is two indexed queries run concurrently (HNSW and GIN), bounded by
  `RAGDESK_RETRIEVAL_CANDIDATES`.
- The API is stateless; scale horizontally behind a load balancer. Postgres is
  the only shared state.
- HNSW memory grows with chunk count. At around 10M chunks per instance,
  partition `chunks` by tenant (ADR 0001).
- Answers are dominated by the model call. Streaming responses are planned (M5).

## Observability

- `/metrics`: `ragdesk_http_requests_total{route,status}`,
  `ragdesk_http_request_duration_seconds{route}`, `ragdesk_answers_total{grounded}`
  and `ragdesk_ingested_chunks_total`.
- JSON logs. `query_log` doubles as the dataset for finding documentation gaps.
- SLO: 99.5% of `/answers` requests succeed over 28 days. Alerting follows the
  burn-rate rules in infra-blueprint.

## Disaster recovery

All state is in Postgres. RPO 5 minutes and RTO 1 hour through point-in-time
restore. Embeddings can be recomputed from document text, so a corrupted
vector index is rebuilt with `REINDEX`, not restored.

## DevOps

- **CI:** ruff, ruff format, mypy strict, pytest on Python 3.12 and 3.13 with a
  pgvector service container, the evaluation gate, and the Docker build.
- **Deploy:** the image runs with the infra-blueprint service chart; migrations
  apply at startup under an advisory lock.
- **Config:** environment variables only (`RAGDESK_*`), validated at startup.

## Testing strategy

| Layer | What | Where |
|---|---|---|
| Domain | Chunking, validation, content hashing | `tests/test_domain.py` |
| API | Auth, scopes, tenant isolation, ingestion dedup, answers and abstention | `tests/test_api.py` |
| Generator | Claude request shape, refusal handling, citation mapping (SDK mocked) | `tests/test_claude_generator.py` |
| Postgres | Migrations, hybrid search, isolation, key lifecycle on real pgvector | `tests/test_postgres.py` |
| Quality | Retrieval metrics against a labelled dataset | `tests/test_evaluation.py`, `ragdesk-eval` |

## Documentation strategy

README for orientation and setup, ADRs for decisions that are expensive to
reverse, this file for cross-cutting concerns, `product.md` for the why.
FastAPI serves the OpenAPI spec at `/docs`.
