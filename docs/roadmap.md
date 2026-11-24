# Roadmap

Open work is tracked as [GitHub issues](https://github.com/jakhongirjp/ragdesk/issues)
under these milestones.

| # | Milestone | Outcome | Status |
|---|---|---|---|
| M1 | Retrieval core | Ingestion, chunking, hybrid search, tenant isolation, Postgres + pgvector | Done (v0.1) |
| M2 | Grounded answers | Citations, abstention, Claude and extractive generators, eval gate | Done (v0.1) |
| M3 | Document formats | PDF, HTML and Markdown parsing with heading-aware chunking | Planned |
| M4 | Access and audit | Key expiry, per-key rate limits, ingest audit log, key management API | Planned |
| M5 | Latency | Streaming answers, embedding cache, load test baseline | Planned |
| M6 | Connectors | Scheduled sync from Confluence and Google Drive with deletes propagated | Planned |
| M7 | Quality | Re-ranking, abstention calibration per collection, larger eval set | Planned |
| M8 | Feedback loop | Thumbs up/down on answers, gap report from ungrounded questions | Planned |
| M9 | Operations | Re-embedding job for model changes, OpenTelemetry traces | Planned |
| M10 | 1.0 | Stable API, SDK, and a published data-retention policy | Planned |

## Release plan

| Version | Contents |
|---|---|
| v0.1 | M1 and M2 |
| v0.2 | M3 and M4 |
| v0.3 | M5 and M7 |
| v0.4 | M6 and M8 |
| v0.5 | M9 |
| v1.0 | M10 |
