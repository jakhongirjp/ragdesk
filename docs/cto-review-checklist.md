# CTO review checklist

Where the project stands. Unchecked items have an issue.

## Architecture
- [x] Ports and adapters; providers swappable by configuration
- [x] One database for documents, vectors, keys and audit (ADR 0001)
- [x] Decisions recorded as ADRs
- [ ] Ingestion moved to a background worker for large documents (M5)

## Answer quality
- [x] Every answer cites its passages; indices mapped server-side
- [x] Abstention before generation, tested
- [x] Offline eval with recall@k, MRR and abstention as a CI gate
- [ ] Abstention rate at 100% on the eval set (currently 2 of 3) (M7)
- [ ] Eval set of at least 100 questions from real traffic (M7)

## Security
- [x] Hash-only key storage, constant-time compare, scopes in the service layer
- [x] Tenant isolation tested on both stores
- [x] Prompt-injection hardening of the context format
- [ ] Per-key rate limiting (M4)
- [ ] Key expiry (M4)
- [ ] Ingest audit trail (M4)

## Operations
- [x] Health, readiness and Prometheus metrics
- [x] Migrations under an advisory lock
- [x] Non-root container image
- [ ] Tracing across retrieval and generation (M9)
- [ ] Re-embedding procedure for an embedding model change (M9)

## Delivery
- [x] CI: lint, format, strict typing, tests on two Python versions with real pgvector
- [x] PR template, issue forms, CODEOWNERS, Dependabot
