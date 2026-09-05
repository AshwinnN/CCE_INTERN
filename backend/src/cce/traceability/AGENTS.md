# Traceability Module Guide

## Status

**PLANNED**

Implemented scaffolding:
- minimal `TraceEvent` dataclass.
- `TraceabilityService.record()` API shape.
- query proto/response fields capable of carrying citations, package/rule/approver/validity/SQL.

Missing:
- answer trace builder;
- lifecycle/query event persistence;
- append-only audit tables/repository;
- complete source → asset → package → answer lineage.

## Purpose

Target ownership: governance and answer lineage/audit semantics. This is separate from engineering telemetry.

## Does NOT Own

- logs/metrics/spans (`observability/`)
- query reasoning
- approval decision logic
- source ingestion itself

## Entry Points

- `backend/src/cce/traceability/service.py::TraceabilityService.record()` — current pass-through.
- `backend/src/cce/traceability/models.py::TraceEvent`.

## Main Flow

### Current

```text
TraceabilityService.record(event) -> event
```

No persistence or answer attachment occurs.

### Target — not implemented

```text
source provenance + proposal history + approved rule + package version + executed SQL
  -> answer trace
  -> append-only audit event(s)
  -> trace fields returned to UI/gRPC/MCP
```

## Important Components

`models.py::TraceEvent`
- minimal trace ID/event type/actor shape.

`service.py::TraceabilityService`
- current no-op persistence facade.

`backend/migrations/cce_control/006_audit.sql`
- target audit schema only; no audit tables.

## Inputs / Outputs

Current input/output:
- arbitrary event in, same event out.

Target input/output:
- governance/query lineage events in; durable append-only audit + answer trace metadata out.

## Dependencies

Target should use a dedicated audit repository/table; current module has none.

## Used By

No production caller found.

## Invariants

### Enforced

None end-to-end.

### Architectural Requirements

- every governed answer has a trace ID;
- rule/package version, approver, validity, source citations and executed SQL are attached where applicable;
- audit data is durable/append-only;
- traceability is not replaced by ordinary application logs.

## Modification Guide

Expected implementation surface:
- trace models/service
- new `persistence/postgres/audit_repository.py`
- `006_audit.sql`
- runtime integration when constructing QueryResponse
- governance integration for lifecycle events

Transport should merely serialize the trace.

## Impact Map

| Change | Usually Modify | Potentially Impacted | Normally Unrelated |
|---|---|---|---|
| Answer trace model | trace service/model + audit repo | runtime response, proto/HTTP/MCP | parser choice |
| Governance audit event | trace/audit repo | governance service | Snowflake discovery |
| Citation lineage | trace builder | runtime/package/provenance contracts | connector observation internals |

## Do Not Inspect Unless Needed

Skip parser/provider internals; consume provenance contracts they already expose.

## Known Gaps / Architecture Mismatch

Expected:
- trace metadata is attached to the answer, not only background logs.

Current:
- query contract has fields, but QueryService does not populate them; audit migration is empty.

Status: **PLANNED**
