# 0002. Hybrid retrieval fused with Reciprocal Rank Fusion

Status: accepted

## Context

Dense embeddings handle paraphrase well and exact identifiers badly. Internal
documents are full of identifiers: error codes, SKU numbers, team names, policy
numbers. Keyword search has the opposite profile.

## Decision

Run both rankings concurrently, 20 candidates each, and merge them with
Reciprocal Rank Fusion (`score = sum 1 / (60 + rank)`). The vector similarity of
the best match is kept separately and used for the abstention decision (ADR 0003).

## Alternatives considered

- **Weighted score sum.** Cosine similarity and `ts_rank` live on different scales
  that shift with the corpus. Weights would need retuning per tenant.
- **Cross-encoder re-ranking.** Better precision, but adds a model call and latency
  to every query. It can be added after fusion later without changing the API.

## Consequences

- No score calibration to maintain. RRF depends only on ranks.
- Two queries per search. Both hit indexes (HNSW and GIN) and run in parallel.
- The eval suite (`ragdesk-eval`) is the arbiter for any change to `k`, candidate
  counts or the fusion constant.
