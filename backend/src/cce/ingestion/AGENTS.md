# Ingestion Module Guide

## Status

**PARTIAL**

Implemented:
- Real LangGraph ingestion workflow.
- Structured Snowflake schema/sample fetch and metadata snapshot persistence.
- MIME-driven parsing and canonical normalization for supported documents.
- DLP/redaction call points.
- SDK HTTP emission hook and file-backed ingestion processing checkpoints.
- Connector-agent-to-ingestion fan-out via `run_pipeline()`.

Missing / incomplete:
- Source RPC/HTTP trigger is not wired to `run_pipeline()`.
- DLP/redaction behavior is a no-op stub.
- Entitlement capture/enforcement is not integrated.
- Downstream SDK emission may be a dry-run; AgenticPlane indexing/graph is not implemented.
- Ingestion does not generate governance proposals.
- Change-observer checkpoint/dedup defaults are memory-only.

## Purpose

Own deterministic ingest-and-ground transformation from source change event to normalized CCE payload/structured metadata, plus processing checkpointing.

## Does NOT Own

- provider authentication/read-only verification (`connectors/`)
- approval state (`governance/`)
- context package assembly (`context_packages/`)
- query-time reasoning (`runtime/`)
- answer trace (`traceability/`)

## Entry Points

- `backend/src/cce/ingestion/service.py::run_pipeline()` — ConnectorAgent → per-event ingestion.
- `backend/src/cce/ingestion/orchestrator.py::run_ingestion()` — executes compiled ingestion workflow.
- `backend/src/cce/ingestion/orchestrator.py::build_ingestion_workflow()` — graph definition.
- `backend/src/cce/ingestion/parsers/factory.py::ParserFactory` — parser selection.

## Main Flow

See `FLOW.md`. In short:

```text
source change event
  -> fetch
  -> structured metadata persist OR document parse
  -> canonical normalize
  -> DLP classify/redact hook
  -> SDK emit/dry-run
  -> processing checkpoint
```

## Important Components

`ingestion/orchestrator.py`
- `IngestionState`
- `fetch_unstructured_node()` / `fetch_structured_node()`
- `persist_structured_metadata_node()`
- `parse_document_node()`
- `normalize_document_node()`
- `classify_for_dlp_node()` / `redact_if_needed_node()`
- `emit_to_sdk_node()`
- `checkpoint_node()`
- `run_ingestion()`

`ingestion/service.py`
- `run_pipeline()` connects the ConnectorAgent event flow to `run_ingestion()`.

`ingestion/models.py`
- canonical document/element/metadata and processing result models.

`ingestion/parsers/factory.py`
- registers Text, CSV, Excel, Docling (PDF/DOCX/PPTX), and PaddleOCR image parsers when imports succeed.

`ingestion/checkpoint.py`
- `IngestionCheckpointStore` is file-backed processing state.
- `InMemoryCheckpointStore` and `InMemoryDedupStore` are used by source observation defaults, not durable processing storage.

`ingestion/change_detection/schema_change_detector.py`
- compares stored snapshots for column add/remove/type changes.

## Inputs / Outputs

Inputs:
- connector change event dict
- connection handle
- source ID
- optional fetch/emit/repository/checkpoint injections

Outputs:
- `PipelineResult` / `IngestionOutcome`
- normalized SDK payload
- structured metadata snapshot IDs/tables/columns when PostgreSQL is configured
- processing checkpoint JSON

## Dependencies

- `connectors/`
- `persistence.ports.MetadataRepository`
- `persistence.postgres.PostgreSQLMetadataRepository`
- `security.dlp`
- LangGraph
- parser libraries (Docling/openpyxl/Pandas/PaddleOCR, depending on MIME)
- `requests` for default SDK emit

## Used By

- Unit/integration tests and direct callers.
- **Not currently used by** `SourceRPCService.TriggerIngestion()` or the HTTP source-ingest endpoint.

## Invariants

### Enforced

- Structured metadata uses a new snapshot ID per persistence run; persisted table/column identities are deterministic within natural keys.
- Parser dispatch is centralized in `ParserFactory`.
- A checkpoint is written at workflow completion even when warnings are present.
- Provider-specific Snowflake fetch closes the connection after use.

### Architectural Requirements — PARTIAL

- DLP/PII must be real before content becomes a proposal: the workflow calls the boundary but implementation is no-op.
- Entitlements should be captured before candidate knowledge and enforced later: not wired.
- All ingested knowledge must land PROPOSED: no proposal model/service is invoked.
- New/changed document should trigger reprocessing and package delta/versioning: only source-event/ingestion part exists; governance/package loop is absent.
- No raw document copy should be retained: this workflow uses temporary files for parsing and deletes them, but downstream SDK/index semantics are outside this repo and cannot be verified here.

## Modification Guide

### Add/change parser

Usually modify:
- `ingestion/parsers/<parser>.py`
- `ingestion/parsers/factory.py`
- parser-focused tests

Potentially modify:
- `ingestion/models.py` only if the canonical contract genuinely changes

Normally do NOT modify:
- connectors registry for a mere file-type change
- runtime/governance/package modules

### Change structured metadata persistence

Usually modify:
- `persist_structured_metadata_node()`
- `persistence/ports.py`
- `persistence/postgres/metadata_repository.py`
- matching migration/tests

Do not mutate historical snapshots to simplify a diff.

### Wire server ingestion trigger

The smallest expected surface is:
- add/implement a source/ingestion application service
- compose it in `bootstrap.py`
- call it from `rpc/services/source_service.py` and `http/app.py`
- persist run state if `GetIngestionStatus` is expected to work

Avoid duplicating the workflow inside transport handlers.

## Impact Map

| Change | Usually Modify | Potentially Impacted | Normally Unrelated |
|---|---|---|---|
| New MIME parser | parser + factory | canonical model tests | governance/runtime |
| Canonical document schema | `models.py` + normalizers | parsers, SDK payload, downstream consumers | RPC health |
| Structured snapshot fields | orchestrator + persistence | migrations, schema change detection | MCP |
| DLP behavior | `security/dlp.py` + workflow tests | normalized/emitted content | connector discovery |
| Trigger wiring | application composition + source transports | run-state persistence | parser internals |

## Do Not Inspect Unless Needed

For parser/normalizer work, normally skip `governance/`, `context_packages/`, `runtime/`, `traceability/`, `mcp/`, `frontend/` and protobuf files.

For structured metadata work, inspect `persistence/` but not governance/runtime.

## Known Gaps / Architecture Mismatch

Expected:
- ingestion creates traceable PROPOSED assets and stops at the human-governance firewall.

Current:
- workflow emits normalized content to `CCE_SDK_ENDPOINT` (or dry-run) and checkpoints; it never calls governance.

Status: **PARTIAL**

Evidence:
- `ingestion/orchestrator.py`
- `governance/service.py`

Expected:
- changed source content is an active loop that eventually creates an approved package-version delta.

Current:
- change-event and reprocessing logic exists, but package/governance version loop does not.

Status: **PARTIAL**
