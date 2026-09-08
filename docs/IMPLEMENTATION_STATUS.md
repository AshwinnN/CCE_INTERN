# CCE implementation status

This document describes the actual backend implementation, not a hosted production acceptance claim.

## Implemented

- Existing Snowflake, Azure Blob and local filesystem integration paths, parsers, normalizers and structured metadata persistence are retained.
- Administrator-created domains and confidence-gated item/query domain routing.
- PostgreSQL source-item identity, item outcomes, candidate staging, source-domain detection history and recoverable leased ingestion jobs.
- Source-level LangGraph fan-out, COMPLETE/PARTIAL gates, same-run resume, changed-again processing and missing-source evidence checks.
- COMPLETE-only per-domain proposal promotion, exact semantic deduplication, merged evidence, conflict ambiguity, CREATE/UPDATE/REMOVE and NO_CHANGE batches.
- Typed seven-kind asset payloads, steward edits, immutable machine proposals, append-only review decisions and automatic terminal-batch package construction.
- Atomic full-snapshot package activation, immutable revisions/history, monotonically increasing versions, BUILD_BLOCKED and soft retirement.
- Relational approved graph projection and manifest-restricted bounded traversal.
- AgenticPlane 1.3 server-side metadata-filtered vector search, package/evidence filtering and explicit insufficient-context behavior.
- Parallel ON/OFF LangGraph branches, structured intent/domain/source selection and shared answer model.
- Shared SQL generation/parse/validation/guard/execution/error-description/retry graph; sqlglot guards, Snowflake timeout and row cap; durable attempts and structured query node/final traces.
- Production HTTP and gRPC domain, proposal-edit, package and dual-branch query contracts; regenerated protobuf code. The MCP helper delegates to the same runtime.
- Task-model settings and deterministic structured Gemini/LiteLLM calls.

## Validation and practical limits

Lifecycle integration tests use real isolated PostgreSQL databases and explicit model/index/warehouse fixtures. They exercise partial resume, no-change, dedupe/conflicts, evidence-aware removal, immutable history, active-version uniqueness, blocked builds, graph depth, lease fencing, SDK request construction, transport contracts and golden query behavior. Hosted Snowflake/AgenticPlane/LLM end-to-end acceptance and benchmark accuracy remain deployment validation, not inferred from fixture results.

The private AgenticPlane SDK was inspected at version 1.3.0. CCE uses its documented `metadata_filter` keyword and JSONB operators. No AgenticPlane source or infrastructure was modified.

DLP now detects/redacts baseline email, SSN and common phone formats; comprehensive enterprise detection is still partial. Actor role checks exist, but deployment must authenticate actor claims upstream; an identity provider, TLS and full gateway integration are not implemented here. Raw `/retrieve` remains a diagnostic API, not a governed answer API, and must not be exposed as a governed alternative.

New source/query/SQL state values use Pydantic models and thin TypedDict graph state. The standalone legacy ingestion/connector utilities retain earlier contracts for compatibility; production source grounding uses typed outputs and confines raw provider dictionaries to its adapter. Standalone legacy runtime helper stubs are not called by the new orchestrator.

## Intentionally outside this MVP

- Continuous source listeners, CDC, webhooks and automatic rule expiry.
- Cross-domain runtime queries, four-tier inheritance and federated database joins.
- CCE data-row authorization beyond the configured warehouse role.
- A LangGraph checkpoint database, Redis/Celery or a CCE graph database.
- A new MCP protocol listener. The existing MCP Python helper is adapted; network MCP transport remains planned.
- A production-connected frontend. `frontend/` and `backend/api/` remain explicitly development mocks; real lifecycle logic is under `backend/src/cce/`.
- Google Docs/Gmail/Slack/other connector implementations absent from this repository.

See [ingestion](architecture/ingestion-flow.md), [governance](architecture/governance-flow.md), [runtime](architecture/runtime-flow.md), and [implementation report](IMPLEMENTATION_REPORT.md) for operational details.
