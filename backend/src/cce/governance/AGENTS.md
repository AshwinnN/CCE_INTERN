# Proposal lifecycle and review

## Entry points

models.py, service.py, state_machine.py

## Responsibilities and invariants

Only PROPOSED -> APPROVED/REJECTED. EDIT preserves machine payload. Every decision is audited. Only terminal batches invoke deterministic packaging. Never auto-approve.

## Validation

Read `docs/IMPLEMENTATION_STATUS.md` and the architecture flow documents for current limits. Use the lifecycle PostgreSQL tests for changes crossing governance, package, ingestion or runtime boundaries. Keep all business rules outside transport adapters and all domain terminology outside core code.
