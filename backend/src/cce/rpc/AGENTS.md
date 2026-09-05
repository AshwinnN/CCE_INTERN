# gRPC Transport Module Guide

## Status

**PARTIAL**

Implemented:
- real `grpc.Server` construction;
- generated protobuf handlers are registered for Health, Source, Query, Governance and Package;
- request/response mapping to shared `Application` services/repositories.

Missing / incomplete:
- Source connection test/ingestion/status behavior;
- real governance/package/query behavior behind handlers;
- authentication/authorization/logging interceptors;
- TLS/secure port configuration.

## Purpose

Own protobuf/gRPC transport mapping only.

## Does NOT Own

- source/provider logic
- ingestion workflow
- governance/package/runtime business logic
- persistence semantics

## Entry Points

- `backend/src/cce/rpc/server.py::create_server()`
- `backend/src/cce/rpc/server.py::serve()`

Services:
- `HealthService`
- `SourceRPCService`
- `QueryRPCService`
- `GovernanceRPCService`
- `PackageRPCService`

## Main Flow

```text
protobuf request
  -> RPC handler
  -> Application service/repository
  -> protobuf response
```

Source registration currently maps directly to `PostgresSourceRepository.save_source()` rather than a Source application service.

## Important Components

`rpc/server.py`
- registers all five generated servicers.
- starts an insecure port.

`rpc/interceptors/correlation.py`
- trace/event ID helpers exist.

`rpc/interceptors/authentication.py`, `authorization.py`, `logging.py`
- empty classes; not supplied to `grpc.server()`.

`rpc/services/source_service.py`
- RegisterSource works; TestConnection/TriggerIngestion/GetIngestionStatus are placeholders.

`rpc/services/query_service.py`
- clean mapping to `QueryService`, whose behavior is currently placeholder.

## Inputs / Outputs

Contracts live in `backend/proto/cce/v1/*.proto`; generated Python lives in `backend/src/cce/gen/cce/v1/`.

Never edit generated files manually.

## Dependencies

- `Application` from `bootstrap.py`
- generated protobuf modules
- application services/repositories

## Used By

- `cce.main` starts this server.

## Invariants

### Enforced

- gRPC uses protobuf-first public contracts.
- query/governance/package transports delegate rather than implement business reasoning inline.

### Architectural Requirements — PARTIAL

- caller authentication/authorization before business service access — not implemented.
- source operations should delegate to an application service — registration currently writes repository directly.
- gRPC and HTTP/MCP must produce the same governed behavior — impossible to verify until runtime exists.

## Modification Guide

For a proto/API change:

Usually modify:
- relevant `backend/proto/cce/v1/*.proto`
- regenerate `backend/src/cce/gen/cce/v1/`
- matching RPC handler mapping
- matching HTTP adapter if surface is shared
- contract tests

Put new behavior in a service before adding transport-specific logic.

## Impact Map

| Change | Usually Modify | Potentially Impacted | Normally Unrelated |
|---|---|---|---|
| New RPC field | proto + handler mapping | HTTP/MCP parity, frontend | parser internals |
| New service behavior | application service first | handler tests | connector registry |
| Auth interceptor | interceptors + server | all gRPC calls | ingestion parser |

## Do Not Inspect Unless Needed

Skip provider internals, parsers and package models for pure transport mapping. Inspect the backing application service and proto only.

## Known Gaps / Architecture Mismatch

Expected:
- source register/test/trigger/status are real server operations.

Current:
- only register is functional; other source methods return placeholder statuses.

Status: **PARTIAL**
