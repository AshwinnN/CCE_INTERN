# Governance Module Guide

## Status

**PLANNED**

Implemented scaffolding:
- `Proposal` dataclass with ID/status only.
- `can_transition()` transition table.
- `require_approved()` helper.
- gRPC/HTTP governance handlers and widened protobuf payload fields.

Missing:
- proposal creation/extraction integration;
- proposal repository/tables;
- list/get/approve/reject behavior;
- approver/timestamp/validity/evidence persistence;
- audit history;
- active approved-only retrieval enforcement.

## Purpose

Target ownership: machine proposal → human review → approve/reject lifecycle and the governance firewall that prevents unapproved knowledge from serving.

## Does NOT Own

- raw document parsing (`ingestion/`)
- package precedence/versioning (`context_packages/`)
- query reasoning (`runtime/`)
- transport serialization (`rpc/`, `http/`)

## Entry Points

Current placeholders:
- `backend/src/cce/governance/service.py::GovernanceService`
- `backend/src/cce/governance/state_machine.py::can_transition()`
- `backend/src/cce/governance/policy.py::require_approved()`

Transports:
- `rpc/services/governance_service.py::GovernanceRPCService`
- HTTP `/proposals...` endpoints in `http/app.py`

## Main Flow

### Current

```text
RPC/HTTP
  -> GovernanceService
      -> [] or NOT_FOUND dictionaries
```

There is no active lifecycle.

### Target — not implemented

```text
ingested candidate + evidence
  -> PROPOSED
  -> human REVIEW
  -> APPROVED or REJECTED
  -> approved asset eligible for package build
  -> append-only lifecycle audit
```

## Important Components

`service.py`
- placeholder API shape.

`state_machine.py`
- transition helper; not connected to persistence/service.

`policy.py`
- approval assertion helper; not enforced at query serving boundary.

`evolution.py`
- `propose_revision()` raises `NotImplementedError`.

`backend/migrations/cce_control/003_governance.sql`
- creates `governance` schema only.

## Inputs / Outputs

Target inputs:
- proposed context asset payload
- evidence/provenance
- reviewer actor and decision
- validity metadata

Target outputs:
- durable proposal state/history
- approved/rejected asset decision

Current outputs are placeholders only.

## Dependencies

No meaningful persistence dependency exists yet. Target implementation should depend on a governance repository, not directly on transport.

## Used By

- current gRPC/HTTP adapters call the placeholder service.
- `context_packages/builder.py` calls the approval helper on supplied assets, but no live package service uses the builder.

## Invariants

### Enforced

None end-to-end.

### Architectural Requirements

- Machine may propose but cannot approve.
- Human approval is mandatory before knowledge changes serving behavior.
- Rejected/proposed assets remain ineligible for runtime/MCP.
- Evidence, provenance, approver, timestamps and validity are retained.
- Lifecycle transitions are auditable, not merely a mutable current status.

## Modification Guide

To implement the minimal real governance vertical slice, expected change surface:

Usually modify/add:
- `governance/models.py`
- `governance/service.py`
- new `persistence/postgres/governance_repository.py`
- `backend/migrations/cce_control/003_governance.sql`
- governance RPC/HTTP mapping only as necessary to expose service responses
- focused tests

Potentially modify:
- ingestion boundary to create proposals after extraction
- traceability service/audit repository for lifecycle events

Normally do NOT modify:
- Snowflake connector
- document parsers
- MCP directly

## Impact Map

| Change | Usually Modify | Potentially Impacted | Normally Unrelated |
|---|---|---|---|
| Proposal fields | model + migration + repository + proto if public | RPC/HTTP, package builder | connectors |
| Approval transition | governance service/repository | package versioning, traceability | parsing |
| Approved-only rule | governance/package/runtime retrieval boundary | MCP indirectly through runtime | source discovery |

## Do Not Inspect Unless Needed

For governance lifecycle work, skip connector provider internals and parsers. Inspect ingestion only where proposal creation is connected; inspect runtime only where approved-only retrieval is enforced.

## Known Gaps / Architecture Mismatch

Expected:
- Propose → Review → Approve firewall with a human actor.

Current:
- service methods do not load or mutate any proposal; migration has no lifecycle table.

Status: **PLANNED**

Evidence:
- `governance/service.py`
- `backend/migrations/cce_control/003_governance.sql`
