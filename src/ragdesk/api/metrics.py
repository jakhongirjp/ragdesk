from prometheus_client import CollectorRegistry, Counter, Histogram

REGISTRY = CollectorRegistry()

HTTP_REQUESTS = Counter(
    "ragdesk_http_requests_total", "HTTP requests", ["route", "status"], registry=REGISTRY
)
HTTP_LATENCY = Histogram(
    "ragdesk_http_request_duration_seconds",
    "HTTP latency",
    ["route"],
    registry=REGISTRY,
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
ANSWERS = Counter("ragdesk_answers_total", "Answers by outcome", ["grounded"], registry=REGISTRY)
INGESTED_CHUNKS = Counter("ragdesk_ingested_chunks_total", "Chunks written", registry=REGISTRY)
