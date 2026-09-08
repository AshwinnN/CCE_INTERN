# CCE PostgreSQL state

## Entry points

postgres/*_repository.py, postgres/lifecycle_db.py, postgres/migrations.py

## Responsibilities and invariants

Use forward migrations. Preserve immutable history. Use short transactions and one connection per worker. Never mutate AgenticPlane internals. Domain locks and unique indexes protect activation and job concurrency.

## Validation

Read `docs/IMPLEMENTATION_STATUS.md` and the architecture flow documents for current limits. Use the lifecycle PostgreSQL tests for changes crossing governance, package, ingestion or runtime boundaries. Keep all business rules outside transport adapters and all domain terminology outside core code.
