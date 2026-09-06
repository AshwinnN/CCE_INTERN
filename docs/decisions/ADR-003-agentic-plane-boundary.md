# ADR-003: AgenticPlane Boundary

CCE consumes AgenticPlane through `cce.integrations.agentic_plane` and does
not depend on AgenticPlane storage or infrastructure internals.

## Status

Accepted, with an MVP local implementation for synthetic and developer testing.

## Decision

CCE code outside `cce.integrations.agentic_plane` depends on a small boundary:
index, search, delete and graph operations. Production AgenticPlane integration
continues to live in `AgenticPlaneClient`.

Until the external AgenticPlane SDK/storage is available in this repo,
`LocalIndexClient` provides a pgvector-backed implementation behind the same
boundary. This keeps server-triggered ingestion searchable without creating a
second ingestion or retrieval architecture.

## Consequences

The local pgvector index may store normalized chunks and embeddings in
`cce_control` for MVP proof. It is not a domain package store, a governance
store, a long-term graph store or a bypass around the approved-context runtime.
