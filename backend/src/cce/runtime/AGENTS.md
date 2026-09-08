# Parallel governed query runtime

## Entry points

orchestrator.py, models.py, sql_pipeline.py, sql_guard.py, sql_executor.py

## Responsibilities and invariants

Only ACTIVE manifest evidence governs ON. OFF never receives package context. Preserve thresholds. Use the shared SQL guard/retry graph. Persist every attempt and final traces. Never claim measured accuracy from proof preference.

## Validation

Read `docs/IMPLEMENTATION_STATUS.md` and the architecture flow documents for current limits. Use the lifecycle PostgreSQL tests for changes crossing governance, package, ingestion or runtime boundaries. Keep all business rules outside transport adapters and all domain terminology outside core code.
