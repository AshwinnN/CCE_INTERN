# Source-level ingestion and recoverable jobs

## Entry points

source_graph.py, grounding.py, lifecycle_models.py, job_runner.py

## Responsibilities and invariants

Discover only on explicit ingest. Stage candidates until COMPLETE. Fence item writes by job claim. Preserve successful unchanged items and retry changed-again items. Legacy grounding stays behind the adapter.

## Validation

Read `docs/IMPLEMENTATION_STATUS.md` and the architecture flow documents for current limits. Use the lifecycle PostgreSQL tests for changes crossing governance, package, ingestion or runtime boundaries. Keep all business rules outside transport adapters and all domain terminology outside core code.
