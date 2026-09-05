# HTTP Adapter Guide

## Status

**PARTIAL**

Implemented:
- FastAPI application and request models.
- health endpoint.
- source registration endpoint.
- governance/package/query endpoints map to the same `Application` objects used by gRPC.

Missing:
- real source test/ingestion/status behavior;
- real governed service behavior behind governance/package/query;
- transport authentication/authorization.

## Purpose

Provide the ADR-004 thin JSON adapter needed by browser/JSON clients. It is a transport, not a second CCE runtime.

## Does NOT Own

Any connector, governance, package, runtime, SQL or trace business logic.

## Entry Points

- `backend/src/cce/http/app.py::create_app()`
- started in a daemon thread by `cce.main` when `settings.http_enabled` is true.

## Main Flow

```text
JSON request -> Pydantic body -> Application service/repository -> JSON mapping
```

## Important Components

`http/app.py`
- Pydantic request bodies: `ActorModel`, `RegisterSourceBody`, `QueryBody`, `ProposalDecisionBody`.
- `create_app()` defines health, source, governance, package and query routes.

## Inputs / Outputs

Inputs:
- JSON request bodies/path parameters.

Outputs:
- JSON mappings of shared repository/service results.
- Current source test/ingestion endpoints return explicit not-implemented status payloads.

## Dependencies

- `Application`
- `QueryRequest`
- FastAPI/Pydantic

## Used By

- intended browser/frontend clients; no frontend implementation currently exists.

## Invariants

### Enforced

- Query/governance/package HTTP endpoints delegate to shared service objects rather than fork runtime logic.

### Architectural Requirements — PARTIAL

- HTTP results must remain semantically equivalent to gRPC/MCP.
- security/auth must be enforced before service access.

## Modification Guide

When adding a backend capability, implement service behavior first. In this file only map JSON ⇄ service types. If complex reasoning appears here, move it out.

## Impact Map

| Change | Usually Modify | Potentially Impacted | Normally Unrelated |
|---|---|---|---|
| JSON body/response shape | `http/app.py` | frontend; possibly proto parity | provider connector |
| New capability | backing service + thin endpoint | RPC/MCP parity | parser code |

## Do Not Inspect Unless Needed

For thin adapter changes, inspect only the backing service and public contract. Do not inspect parser/provider internals.

## Known Gaps / Architecture Mismatch

Expected:
- UI can trigger real source ingestion and governed query lifecycle.

Current:
- source test/ingest/status are hardcoded placeholders and runtime/governance/package services are not implemented.

Status: **PARTIAL**
