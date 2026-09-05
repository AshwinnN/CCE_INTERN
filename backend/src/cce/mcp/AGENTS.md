# MCP Module Guide

## Status

**PLANNED**

Implemented scaffolding:
- a thin Python `query()` helper that delegates to `QueryService`.
- `create_mcp_server(app)` placeholder returning the query service in a dict.

Missing:
- MCP protocol server transport;
- tool registration/schema;
- context/search/term/guarded-query tools described by target architecture;
- security/authorization;
- governed runtime behavior to expose.

## Purpose

Target ownership: expose existing CCE application/runtime capabilities over MCP without creating a second reasoning implementation.

## Does NOT Own

- context resolution logic
- SQL generation/execution logic
- package selection
- governance policy

## Entry Points

- `backend/src/cce/mcp/server.py::create_mcp_server()`
- `backend/src/cce/mcp/tools/query.py::query()`

## Main Flow

### Current

```text
Python caller -> mcp.tools.query.query() -> QueryService.query() -> placeholder response
```

There is no network/protocol MCP server.

### Target — not implemented

```text
external MCP client
  -> MCP tool
  -> same QueryService/runtime used by gRPC/HTTP
  -> governed response + trace
```

## Important Components

`mcp/server.py`
- placeholder construction function; no protocol library/listener.

`mcp/tools/query.py`
- thin Python adapter creating `QueryRequest` and delegating to `QueryService`.

## Inputs / Outputs

Current:
- Python `question` string + metadata → `QueryResponse` from the placeholder runtime.

Target:
- MCP tool call → governed runtime response/trace.

## Dependencies

- `runtime.service.QueryService`

## Used By

No production MCP listener/consumer exists in this repository.

## Invariants

### Enforced

None as a protocol boundary.

### Architectural Requirements

- MCP must not bypass approval, entitlement or SQL guards.
- MCP is a thin adapter over the same runtime as other transports.
- external agents do not receive direct database credentials/access through CCE.

## Modification Guide

Implement the protocol adapter only after/alongside a real QueryService contract. Keep MCP tool functions thin. Do not copy runtime orchestration into MCP handlers.

## Impact Map

| Change | Usually Modify | Potentially Impacted | Normally Unrelated |
|---|---|---|---|
| MCP protocol/tool registration | `mcp/` | QueryService contract/security | parser code |
| governed answer shape | runtime first, then MCP mapping | gRPC/HTTP parity | connector observation |

## Do Not Inspect Unless Needed

For MCP transport work, inspect runtime/public contracts and security. Skip ingestion/parser internals.

## Known Gaps / Architecture Mismatch

Expected:
- Universal MCP broker exposes governed context and guarded query tools.

Current:
- `create_mcp_server()` is not a protocol server.

Status: **PLANNED**
