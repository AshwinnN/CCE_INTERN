# Shared-runtime MCP helper

## Entry points

tools/query.py

## Responsibilities and invariants

Delegate all questions/domain selection to QueryService. The Python helper is implemented; a network MCP protocol listener remains planned.

## Validation

Read `docs/IMPLEMENTATION_STATUS.md` and the architecture flow documents for current limits. Use the lifecycle PostgreSQL tests for changes crossing governance, package, ingestion or runtime boundaries. Keep all business rules outside transport adapters and all domain terminology outside core code.
