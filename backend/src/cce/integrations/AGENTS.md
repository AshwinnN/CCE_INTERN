# External SDK/model boundaries

## Entry points

agentic_plane/client.py, agentic_plane/local_index.py, llm/client.py

## Responsibilities and invariants

AgenticPlane >=1.3 metadata_filter is verified. Preserve domain/source/run provenance. Graph results supplement runtime evidence only when their source memories are domain-scoped; original passages establish precise policy facts. Structured LLM requests and results use Pydantic; task models fall back to the shared model.

## Validation

Read `docs/IMPLEMENTATION_STATUS.md` and the architecture flow documents for current limits. Use the lifecycle PostgreSQL tests for changes crossing governance, package, ingestion or runtime boundaries. Keep all business rules outside transport adapters and all domain terminology outside core code.
