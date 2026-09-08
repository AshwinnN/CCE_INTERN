# Immutable domain package lifecycle

## Entry points

builder.py, validator.py, models/assets.py, service.py

## Responsibilities and invariants

One package per domain. Build full snapshots. Lock domain and activate within one transaction. Validate references and SQL. Block structurally invalid builds; never mutate approved historical revisions.

## Validation

Read `docs/IMPLEMENTATION_STATUS.md` and the architecture flow documents for current limits. Use the lifecycle PostgreSQL tests for changes crossing governance, package, ingestion or runtime boundaries. Keep all business rules outside transport adapters and all domain terminology outside core code.
