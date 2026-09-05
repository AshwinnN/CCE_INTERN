# Runtime Module Guide

## Status

**PLANNED**

Implemented scaffolding:
- request/response dataclasses with expanded trace/package/SQL fields.
- function/module boundaries for intent, retrieval, entities, packages, rules, semantics, ambiguity, live-data decision, SQL generation/guard/execution and proof comparison.
- a minimal `enforce_select_only()` helper.

Missing:
- actual query reasoning/orchestration;
- governed retrieval;
- package/rule/entity/semantic resolution;
- verified SQL lookup/generation;
- guarded live execution;
- business rule application;
- Context OFF execution;
- Context ON execution;
- OFF-vs-ON comparison and answer explanation.

## Purpose

Target ownership: resolve a business question against approved package context, optionally obtain bounded live data, produce the governed answer, and run/compare the ungoverned baseline.

## Does NOT Own

- source ingestion
- proposal approval
- package persistence/authoring
- transport serialization
- provider-specific credential verification

## Entry Points

- `backend/src/cce/runtime/service.py::QueryService.query()` — currently returns a fixed not-implemented answer.
- `backend/src/cce/runtime/orchestrator.py::RuntimeOrchestrator.run()` — same placeholder behavior.

## Main Flow

### Current

```text
QueryRequest
  -> QueryService.query()
  -> QueryResponse(answer="CCE query runtime is not implemented yet.")
```

No other runtime helper is invoked.

### Target — not implemented

```text
question
  -> intent / entities / ambiguity
  -> resolve approved package + applicable rules
  -> retrieve approved evidence
  -> determine live-data need
  -> verified SQL first / candidate SQL if allowed
  -> SQL guard
  -> read-only bounded execution
  -> apply rule + explain context
  -> Context ON answer

question -> Context OFF baseline
OFF + ON -> compare/proof -> answer trace
```

## Important Components

`service.py`
- `QueryRequest`, `QueryResponse`, `QueryService`.

`orchestrator.py`
- `RuntimeOrchestrator`; placeholder.

`intent.py`, `entity_resolution.py`, `package_resolver.py`, `rule_resolver.py`, `semantic_resolver.py`, `ambiguity.py`, `live_data.py`
- placeholder functions returning empty/default values.

`retrieval.py`
- delegates to `AgenticPlaneClient.retrieve()`, which currently returns `[]`.

`sql_generator.py`
- raises `NotImplementedError`.

`sql_guard.py`
- checks only `sql.strip().lower().startswith("select")`.

`sql_executor.py`
- raises `NotImplementedError`.

`proof.py`
- returns `{}`.

## Inputs / Outputs

Input:
- `QueryRequest(question, actor_id, context_enabled, metadata)`

Output contract:
- `QueryResponse` supports answer, trace ID, citations, context used, applied rule, package ID/version, executed SQL, approver, validity and confidence.

Current implementation populates only the fixed answer plus optional metadata trace ID.

## Dependencies

- `integrations.agentic_plane` in retrieval
- future package/governance/traceability repositories/services
- structured connector execution behind a runtime executor

## Used By

- `rpc/services/query_service.py`
- HTTP `POST /query`
- `mcp/tools/query.py`

## Invariants

### Enforced

None of the product runtime invariants are end-to-end enforced because no real runtime path executes.

### Architectural Requirements

- only APPROVED context can be selected;
- ambiguity must be surfaced/resolved rather than guessed;
- verified SQL should be preferred where applicable;
- every executed statement must be SELECT-only, bounded by row cap and timeout, and run through read-only credentials;
- Context OFF and Context ON are separate paths and comparable;
- Context ON explanation must include rule/package/source provenance and validity;
- all transports call the same runtime.

## Modification Guide

Implement in dependency order rather than filling every placeholder independently:

1. define real context/package/retrieval contracts;
2. implement approved-only package/rule resolution;
3. implement verified SQL selection + SQL guard + executor;
4. implement Context ON orchestration;
5. implement Context OFF baseline;
6. implement comparison/proof;
7. attach traceability;
8. keep QueryService as the stable application entry point.

Usually modify:
- `runtime/*` relevant to the feature
- package/governance repository/service only for missing input contracts
- `traceability/` for answer trace

Normally do NOT modify:
- parser implementation
- connector registry unless live data requires a new provider
- MCP transport logic beyond mapping the final runtime response

## Impact Map

| Change | Usually Modify | Potentially Impacted | Normally Unrelated |
|---|---|---|---|
| Query response semantics | runtime service/orchestrator | proto/RPC/HTTP/MCP, traceability | ingestion parser |
| Rule resolution | runtime rule/package resolver | package model, governance | source discovery |
| SQL safety | sql guard/executor | structured connector execution | DLP parser |
| OFF/ON proof | proof/orchestrator | query contract/UI | persistence metadata ingestion |

## Do Not Inspect Unless Needed

For runtime reasoning, skip parser internals and connector observation logic. Inspect connector execution only at the SQL executor boundary; inspect governance/package code for approval and package contracts.

## Known Gaps / Architecture Mismatch

Expected:
- runtime is the proof engine: Context OFF and Context ON both execute, Context ON uses approved packages and guarded SQL.

Current:
- `QueryService.query()` returns a literal not-implemented message; helper modules are not called.

Status: **PLANNED**

Expected:
- SELECT-only + timeout + row cap are a hard execution boundary.

Current:
- prefix-only helper exists but is disconnected; Snowflake raw executor has no row cap/statement timeout.

Status: **PARTIAL helper / PLANNED end-to-end enforcement**
