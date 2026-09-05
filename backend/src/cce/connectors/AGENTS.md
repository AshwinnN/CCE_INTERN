# Connectors Module Guide

## Status

**PARTIAL**

Implemented:
- Provider-neutral request/response/change-event contracts.
- Connector routing/validation and observation orchestration.
- Real Snowflake connector with live read-only write probe, schema discovery, row counts, one sample row/table, and raw query execution.
- Real Azure Blob SDK helper(s) for listing/processing or per-object fetching.

Missing / incomplete:
- Structured factory implements only Snowflake while registry marks several other adapters READY.
- Unstructured observation needs caller-injected provider listers; provider-proof read-only/entitlement behavior is mostly declarative.
- Durable observation checkpoint/dedup storage is not wired.
- Server Source TestConnection/TriggerIngestion does not invoke these paths.

## Purpose

Own provider connection, discovery/read operations, source change observation, connector-normalized errors/contracts, and source-side safety checks.

## Does NOT Own

- parsing/normalization after raw fetch (`ingestion/`)
- governance approval (`governance/`)
- domain packages (`context_packages/`)
- query reasoning/SQL policy (`runtime/`)
- transport handlers (`rpc/`, `http/`, `mcp/`)

## Entry Points

- `backend/src/cce/connectors/agent.py::ConnectorAgent.handle()` — registry → validation → route → connect → optional observe.
- `backend/src/cce/connectors/factory.py::ConnectorFactory.create()` — structured connector factory.
- `backend/src/cce/connectors/structured/snowflake/connector.py::SnowflakeConnector` — current executable structured provider.
- `backend/src/cce/connectors/fetch.py::{snowflake_schema_fetcher, azure_blob_fetcher}` — real provider fetch helpers used/available to ingestion.

## Main Flow

```text
ConnectorRequest
  -> StubAdapterRegistryProvider.get()
  -> validate_registry_entry()
  -> check_requested_capabilities()
  -> route by structured/unstructured kind
  -> connect_structured() / connect_unstructured()
  -> optional StructuredChangeObserver / UnstructuredChangeObserver
  -> ConnectorResponse + change_events
```

For structured ingestion, `snowflake_schema_fetcher()` creates a fresh `SnowflakeConnector`, performs the live write probe, calls `get_schema_card()`, then closes the connection.

## Important Components

`connectors/contracts.py`
- `ConnectorRequest`, `ConnectorResponse` and source change-event shapes.

`connectors/registry.py`
- `StubAdapterRegistryProvider`; advertises adapter metadata/capabilities.
- Warning: `status="READY"` is not implementation proof.

`connectors/factory.py`
- `ConnectorFactory`; current default map contains only `snowflake`.

`connectors/agent.py`
- `ConnectorAgent`; orchestrates fail-closed registry/capability/connect/observe behavior.

`connectors/observation.py` and `ingestion/change_detection/documents.py`
- Observer contracts and change-event generation.

`connectors/structured/snowflake/connector.py`
- `SnowflakeConnector.connect()`, `get_schema_card()`, `execute_query()`.

`connectors/unstructured/azure_blob/connector.py`
- `AzureBlobSource.process_blobs()`; SDK-backed direct parse path, not the path used by `azure_blob_fetcher()`.

## Inputs / Outputs

Inputs:
- `ConnectorRequest`
- persisted or environment-derived source config
- credential references
- optional object/catalog lister callbacks

Outputs:
- `ConnectorResponse`
- connection metadata
- source change events
- raw bytes or schema card when fetch helpers are called

## Dependencies

- `cce.security.credentials`
- Snowflake connector SDK / cryptography
- Azure Blob SDK for Azure helpers
- ingestion change-observer classes for observation

## Used By

- `backend/src/cce/ingestion/service.py::run_pipeline()`
- `backend/src/cce/ingestion/orchestrator.py` structured/unstructured fetch nodes
- tests and source integration scripts

## Invariants

### Enforced

- **Snowflake read-only credential proof:** `SnowflakeConnector.connect()` rejects a credential when `CREATE TEMPORARY TABLE` succeeds.
- Snowflake connector closes after production schema fetch.
- Structured factory rejects unsupported adapter keys instead of silently falling back.

### Architectural Requirements — PARTIAL

- All source connectors must be read-only/least privilege. Only Snowflake has a real provider write probe.
- Change observation should be durable. Default `InMemoryCheckpointStore`/`InMemoryDedupStore` are process-local.
- Entitlement capture should reflect provider permissions; current unstructured handle marks this from registry capability metadata rather than a provider verification.
- Registry support claims should correspond to executable connector implementations; they currently do not.

## Modification Guide

### Add a structured connector

Usually modify:
- `connectors/structured/<adapter>/...`
- `connectors/factory.py`
- `connectors/registry.py` only after executable capability exists
- focused unit/integration tests

Potentially modify:
- canonical type mapping if the provider introduces new native types
- config/credential assembly

Normally do NOT modify:
- `governance/`
- `context_packages/`
- `runtime/`
- `mcp/`

### Add an unstructured provider

Usually modify:
- provider implementation or lister/fetcher under `connectors/`
- registry descriptor only after the provider path works
- observation/fetch integration tests

Potentially modify:
- parser factory only for a new content type, not a new source provider

### Tighten SQL safety

Connector-level read-only verification belongs here. Query semantics/SELECT parsing, timeout and row-cap policy belong in `runtime/`; do not make provider code the sole runtime governance guard.

## Impact Map

| Change | Usually Modify | Potentially Impacted | Normally Unrelated |
|---|---|---|---|
| Snowflake auth/discovery | `structured/snowflake/` | config, credential resolver, ingestion structured fetch | governance, packages, MCP |
| New structured provider | provider + factory + registry | canonical types, ingestion metadata | frontend, governance |
| New document source | provider lister/fetcher + registry | change observer, ingestion fetch | runtime proof |
| Change change-event contract | `contracts.py` | connector agent, ingestion service/checkpoints | package models |

## Do Not Inspect Unless Needed

For connector-local changes, skip `governance/`, `context_packages/`, `runtime/`, `traceability/`, `mcp/`, and `frontend/` unless a cross-module contract is being changed.

## Known Gaps / Architecture Mismatch

Expected:
- Registry READY adapters are available to the product.

Current:
- `ConnectorFactory._connectors` includes only Snowflake. Postgres/Databricks/BigQuery and most unstructured adapters have no equivalent executable provider implementation.

Status: **PARTIAL**

Evidence:
- `connectors/registry.py`
- `connectors/factory.py`

Expected:
- read-only SELECT execution is bounded by runtime SQL guard, timeout and row limit.

Current:
- Snowflake connection is read-only-proven, but `execute_query()` accepts arbitrary SQL and fetches all returned rows; no runtime guard calls it.

Status: **PARTIAL**

Evidence:
- `connectors/structured/snowflake/connector.py`
- `runtime/sql_guard.py`
- `runtime/sql_executor.py`
