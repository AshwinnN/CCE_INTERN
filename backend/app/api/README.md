# CCE Tool REST API

This is the HTTP boundary for the CCE Tool server.

## Live

- `GET /health` — liveness check
- `GET /` — server information
- `GET /docs` — FastAPI/OpenAPI documentation
- `POST /api/v1/memory/store` — delegates to `plane.memory.store(...)`
- `POST /api/v1/memory/store-batch` — delegates to `plane.memory.store_batch(...)`
- `POST /api/v1/memory/search` — delegates to `plane.memory.search(...)`

## MVP placeholders

The following routes are registered to match the current MVP flow but return
HTTP 501 until their implementation is built:

- ingestion events
- context/entity resolution
- governed context assembly
- human review approve/reject
- domain package retrieval
- governed query
- compare & answer
- traceability
- MCP manifest

The placeholder routes are intentionally explicit; they do not return fake
business results.
