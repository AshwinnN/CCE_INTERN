# ADR-005: Workspace replaces Domain as the MVP runtime/governance scope

## Status

Accepted and implemented.

## Context

CCE was originally domain-centric: an administrator created named `Domain`
rows, ingestion detected which domain(s) a source item belonged to with an LLM
call, a query optionally selected a `domain_id` (or an LLM resolved one from
several ambiguous candidates), and governance/packages/retrieval were all
scoped by `domain_id`. In practice this added an LLM-driven routing step with
its own failure modes (`WORKSPACE_UNRESOLVED`/ambiguous-candidate handling)
for a concept that added little value over "the operator already knows which
named scope a source and a query belong to."

The MVP also needed: a controlled six-connector source catalog with
pre-registration discovery and schema selection, multi-question atomization so
a compound question gets one full dual-path (Context ON/OFF) proof per atomic
question instead of one proof over an already-blended answer, and a feedback
loop so upvotes/downvotes shape future answering.

## Decision

Replace `Domain` with `Workspace` as the single top-level governance/runtime
scope, with a strictly simpler hierarchy:

```
Workspace -> Sources -> exactly one Context Package (v1, v2, v3, ...)
```

Concretely:

- `workspace` replaces `domain` (migration `014_workspace_scope.sql`):
  `workspace_id` is a human-readable, immutable identifier derived as
  `{name}_workspace` at creation time (no slug/lowercase/random generation);
  `name` is renamable; names are case-insensitive unique; deletion is
  soft/archive-only. Workspace creation is transactional with creating its one
  `context_package` row (no `v1` until the first approved proposal batch).
- Every domain-scoped table (`cce_source`, `candidate_extraction`,
  `proposal_batch`, `context_asset`, `context_package`, `graph_entity`,
  `graph_edge`, `query_trace`) is re-owned by `workspace_uuid`.
  `source_domain`/`source_domain_detection` and LLM domain
  detection/routing are removed entirely, not deprecated in place.
  `DOMAIN_UNRESOLVED`/`detected_domains` are removed from ingestion state;
  externally visible ingestion status is normalized to
  `RUNNING`/`SUCCESS`/`PARTIAL`/`FAILED` (`COMPLETE` removed).
- A query always executes directly at Workspace scope
  (`POST /workspaces/{workspace_id}/query`); there is no domain dropdown, no
  `domain_id`, and no domain-routing LLM call. A Workspace with no active
  approved package version rejects the query with a structured
  `NO_ACTIVE_PACKAGE` 409 rather than silently answering Context-OFF-only.
- A real source-type catalog (`sources/catalog.py`) replaces an ad hoc
  connector list: six production READY types (Snowflake, PostgreSQL, SQL
  Server, MySQL, Azure Blob, Google Drive), each with a typed Pydantic config
  model driving both backend validation and dynamic frontend forms, plus
  pre-registration discovery (`/workspaces/{workspace_id}/sources/discover`)
  and an explicit `all`/`selected` schema-selection contract.
- Multi-question atomization (`runtime/compound.py`) splits a compound
  question into 1-10 standalone atomic questions (LLM call, Pydantic-enforced
  max, never silently truncated), fans each one out to its own complete
  Context ON/OFF subgraph (`runtime/orchestrator.py`, unchanged internally
  except that it now receives an already-resolved Workspace/package instead of
  doing domain resolution itself), retrieves Workspace-scoped feedback lessons
  per atomic question, and synthesizes a final answer only from successful
  Context ON answers -- a failed atomic question is reported, never fabricated.
- Feedback memory (`runtime/feedback.py`) persists upvotes/downvotes
  (optional comment; an LLM critique when a downvote has no comment) as
  governed metadata in PostgreSQL (`query_feedback`), gated at `>=0.70`
  confidence for eligibility as a future few-shot lesson. Feedback
  *embeddings* are never a bespoke Postgres `vector` column: eligible feedback
  is indexed through the same `index_client` boundary (AgenticPlane in
  production, `LocalIndexClient`/pgvector only in local/offline mode) already
  used for every other embedding in the system, and retrieval is scoped to the
  Workspace and filtered per atomic question through that same boundary. This
  follows the codebase's existing, established pattern -- migration
  `008_local_index.sql` already made pgvector strictly opt-in behind
  `CCE_INDEX_BACKEND=local` -- so the control-plane Postgres database never
  needs the `vector` extension in production (`agentic_plane` backend),
  including on managed Postgres services that do not allow-list it (e.g. Azure
  Database for PostgreSQL).
- gRPC/HTTP contracts are unified: `domains.proto`/`governance.proto`/
  `packages.proto`/`query.proto`/`retrieval.proto`/`sources.proto` and their
  per-concept RPC services are removed. A single `WorkspaceService` RPC
  (`workspaces.proto`) and a single `workspaces/operations.py::Operations`
  action-dispatch boundary back both the HTTP and gRPC adapters, so the two
  transports cannot drift.
- The frontend is Workspace-first (`/workspaces`, `/workspaces/new`,
  `/workspaces/:workspaceId/{sources,proposals,package,query}`); there is no
  Domain route, no domain dropdown and no Context ON/OFF toggle. No internal
  UUID (workspace, source, package, package version, proposal, evidence,
  trace, ingestion run, chunk) is rendered as a user-facing identifier --
  human-readable names/labels are used instead, with UUIDs retained only in
  API/audit payloads.

## Consequences

- This is an MVP-breaking change by design: there is no dual-write or
  read-compatibility shim for `Domain`. Migration `014_workspace_scope.sql`
  fails clearly (rather than guessing) when existing development data has an
  ambiguous or missing domain-to-source association, instead of silently
  assigning incorrect Workspace ownership.
- Every repository method takes a `workspace_uuid`/`workspace_id` and enforces
  it at the query level (not just at the frontend/routing layer), so a source,
  proposal, package or piece of feedback from one Workspace cannot be reached
  through another Workspace's scope.
- Query latency increases somewhat versus a single-question single-domain
  query, because atomization adds one LLM call up front and each atomic
  question now runs its own full dual-path proof rather than sharing one
  proof across a blended answer. This trade-off was accepted because it keeps
  the ON/OFF proof meaningful per claim instead of averaging it over a
  multi-part answer.
- Existing "COMPLETE" or "domain" references anywhere in code, tests, or
  operational documentation are treated as leftover naming debt to be fixed,
  not as an alternate accepted vocabulary.
