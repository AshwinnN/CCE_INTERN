# gRPC protobuf adapters

## Entry points

services/, server.py, ../../../../proto/cce/v1/

## Responsibilities and invariants

Keep parity with shared services. Regenerate through scripts/generate_proto.py; never edit generated files manually. Do not implement runtime or governance logic in adapters.

## Validation

Read `docs/IMPLEMENTATION_STATUS.md` and the architecture flow documents for current limits. Use the lifecycle PostgreSQL tests for changes crossing governance, package, ingestion or runtime boundaries. Keep all business rules outside transport adapters and all domain terminology outside core code.
