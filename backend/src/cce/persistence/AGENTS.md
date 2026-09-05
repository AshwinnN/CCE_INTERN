# Persistence Module Guide

## Status

**PARTIAL**

Implemented:
- PostgreSQL migration runner.
- Source registration write.
- Structured source → namespace → schema → immutable snapshot persistence.
- Tables, columns, constraints, relationships and relationship-column mappings.
- Retrieval/diff methods for structured metadata.

Missing:
- governance, context-package, runtime and audit repositories/tables.
- durable Postgres checkpoint repository.
- source repository read/list/run-state methods.

## Purpose

Own CCE-managed durable state and persistence interfaces. Current durable functionality is concentrated in registration and structured metadata.

## Does NOT Own

- provider network reads (`connectors/`)
- ingestion orchestration (`ingestion/`)
- governance decisions (`governance/`)
- query reasoning (`runtime/`)
- transport mapping

## Entry Points

- `backend/src/cce/persistence/postgres/migrations.py::initialize_control_postgres()`
- `backend/src/cce/persistence/postgres/metadata_repository.py::PostgreSQLMetadataRepository`
- `backend/src/cce/persistence/postgres/source_repository.py::PostgresSourceRepository.save_source()`
- `backend/src/cce/persistence/ports.py::MetadataRepository`

## Main Flow

```text
bootstrap
  -> initialize_control_postgres()
  -> applies backend/migrations/cce_control/*.sql

structured ingestion
  -> MetadataRepository.ensure_source/namespace/schema
  -> save_snapshot
  -> save_table/save_column/(constraint/relationship)
  -> later list/diff by snapshot
```

## Important Components

`persistence/ports.py`
- `MetadataRepository` contract.
- `SchemaSnapshot`, `SchemaChange`.

`postgres/metadata_repository.py`
- deterministic UUID helper `_stable_uuid()`.
- real PostgreSQL implementation with connection pool.

`postgres/source_repository.py`
- minimal source-registration write only.

`postgres/checkpoint_repository.py`
- explicit stub; `save_checkpoint()` raises `NotImplementedError`.

`backend/migrations/cce_control/001_registry.sql`
- `cce_source`, `cce_namespace`, `cce_schema`.

`002_metadata*.sql`
- structured snapshot/table/column/constraint/relationship state.

`003_governance.sql` through `006_audit.sql`
- create target schemas only; no functional tables.

## Inputs / Outputs

Inputs:
- source identifiers/config references
- schema snapshot/table/column/constraint/relationship records

Outputs:
- durable PostgreSQL rows
- snapshot IDs and metadata query results

## Dependencies

- PostgreSQL / `psycopg2`

## Used By

- `bootstrap.py`
- source RPC/HTTP registration
- structured ingestion metadata persistence
- schema change detector

## Invariants

### Enforced

- Structured historical data is snapshot-scoped.
- Table/column/constraint/relationship identity is deterministic via UUID5-like stable keys while row version is snapshot-scoped.
- Migration runner applies repository migration files in sorted order.

### Architectural Requirements — PARTIAL

- ADR-002 says registry, metadata, governance, context, runtime and audit CCE state belongs in `cce_control`; only registry/metadata are materially implemented.
- Governance/audit should preserve lifecycle history; no tables exist yet.

## Modification Guide

### Add structured metadata field

Usually modify:
- matching `002_metadata*.sql` migration strategy
- `MetadataRepository` contract if public
- `PostgreSQLMetadataRepository`
- ingestion persistence node
- repository tests

Preserve historical snapshot semantics.

### Implement governance/package/runtime/audit persistence

Use the existing module boundary, but do not force these entities into structured metadata tables. Implement purpose-specific repositories/migrations under the target schemas.

### Change source registration

Current `PostgresSourceRepository.save_source()` stores `credential_ref` in `cce_source.display_name`; fixing this requires a migration/schema decision plus service/read methods, not just renaming a Python variable.

## Impact Map

| Change | Usually Modify | Potentially Impacted | Normally Unrelated |
|---|---|---|---|
| Metadata table schema | migration + repository | ingestion, schema change tests | MCP/UI |
| Source registry schema | `001_registry.sql` + source repository | source RPC/HTTP/bootstrap | parser code |
| New governance store | `003_governance.sql` + new repository | governance service, audit | connectors |
| New package store | `004_context.sql` + new repository | package/runtime | parser internals |

## Do Not Inspect Unless Needed

Structured metadata changes normally do not require `mcp/`, `frontend/`, `context_packages/`, or `runtime/` unless the change creates a new runtime contract.

## Known Gaps / Architecture Mismatch

Expected:
- all CCE control-plane state in `cce_control`.

Current:
- `003_governance.sql`, `004_context.sql`, `005_runtime.sql`, and `006_audit.sql` explicitly contain only `CREATE SCHEMA` placeholders.

Status: **PARTIAL**

Expected:
- persisted source config can be retrieved to test/trigger ingestion.

Current:
- `PostgresSourceRepository` only has `save_source()` and stores credential reference in `display_name`.

Status: **PARTIAL**
