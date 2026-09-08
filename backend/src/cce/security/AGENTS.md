# Credential and baseline DLP boundaries

## Entry points

credentials.py, dlp.py

## Responsibilities and invariants

Credential references stay out of logs. DLP covers baseline email/SSN/phone patterns and is not comprehensive. Authentication infrastructure remains separate from actor-role assertions. No CCE row-level authorization engine for this MVP.

## Validation

Read `docs/IMPLEMENTATION_STATUS.md` and the architecture flow documents for current limits. Use the lifecycle PostgreSQL tests for changes crossing governance, package, ingestion or runtime boundaries. Keep all business rules outside transport adapters and all domain terminology outside core code.
