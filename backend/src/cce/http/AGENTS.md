# Thin production HTTP adapter

## Entry points

app.py

## Responsibilities and invariants

Map typed requests/responses to shared services. Domain creation requires ADMIN and proposal decisions STEWARD. Actor claims need authenticated upstream provenance. Branch failures retain the structured query schema.

## Validation

Read `docs/IMPLEMENTATION_STATUS.md` and the architecture flow documents for current limits. Use the lifecycle PostgreSQL tests for changes crossing governance, package, ingestion or runtime boundaries. Keep all business rules outside transport adapters and all domain terminology outside core code.
