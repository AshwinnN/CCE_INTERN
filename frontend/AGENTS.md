# Frontend Guide

## Status

**PLANNED**

Current repository evidence:
- `frontend/README.md` only.
- no application source, package manifest, build config, pages or client implementation found.

## Purpose

Target user interfaces from the product documents include steward governance review and the Context OFF/Context ON proof workspace.

## Does NOT Own

Backend reasoning, approval enforcement, SQL safety, source access or trace construction. The UI should display/call backend results, not recreate these rules.

## Entry Points

None in the current repository.

## Main Flow

### Current

No executable frontend flow exists.

### Target — not implemented

```text
browser -> JSON adapter -> shared backend services/runtime -> rendered governance/proof/trace state
```

## Important Components

`frontend/README.md`
- only frontend file in the current snapshot; no framework/application code.

## Inputs / Outputs

Target inputs:
- source/proposal/package/query JSON responses from the backend adapter.

Target outputs:
- steward decisions and analyst questions sent through backend APIs; proof/trace rendered to user.

## Dependencies

Target browser integration should use the thin JSON adapter (`backend/src/cce/http/app.py`) rather than direct database access.

## Used By

Target human users: domain steward/analyst. No current executable consumer.

## Invariants

### Enforced

None; no frontend exists.

### Architectural Requirements

- show evidence before human approval;
- show OFF/ON comparison and why Context ON differs;
- expose package/rule/source trace fields returned by backend;
- never implement a client-side bypass of approved-only or SQL guards.

## Modification Guide

When frontend implementation begins, treat HTTP as a transport over shared backend services. Do not infer unsupported endpoint behavior from proto fields; check `docs/IMPLEMENTATION_STATUS.md` first.

## Impact Map

| Change | Usually Modify | Potentially Impacted | Normally Unrelated |
|---|---|---|---|
| Build initial UI | future frontend app | HTTP contract | connector internals |
| Proof view | future proof page/client | runtime response/trace fields | parser implementation |
| Governance queue | future governance page/client | governance JSON API | Snowflake schema discovery |

## Do Not Inspect Unless Needed

Backend connector/parser internals are irrelevant to UI work unless an API contract is being designed.

## Known Gaps / Architecture Mismatch

Expected:
- analyst/steward application.

Current:
- no implementation.

Status: **PLANNED**
