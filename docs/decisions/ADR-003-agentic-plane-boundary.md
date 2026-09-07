# ADR-003: AgenticPlane Boundary

CCE consumes AgenticPlane through `cce.integrations.agentic_plane` and does
not depend on AgenticPlane storage or infrastructure internals.

## Status

Accepted. The production vector write/search/delete adapter is SDK-backed;
the local implementation remains available for offline and developer testing.

## Decision

CCE code outside `cce.integrations.agentic_plane` depends on a small boundary:
index, search, delete and graph operations. Production AgenticPlane integration
lives in `AgenticPlaneClient`. It sends raw chunk text to AgenticPlane for
server-side embedding and records only the returned memory references in CCE's
`cce_agentic_plane_memory` bridge table. AgenticPlane owns chunk text and
vectors; CCE owns references, source provenance, governance, approvals and
audit state.

`LocalIndexClient` provides a pgvector-backed implementation behind the same
boundary for offline use. Both implementations share payload chunking and
expose cosine-similarity scores where higher is better. This keeps
server-triggered ingestion searchable without creating a second ingestion or
retrieval architecture.

## Consequences

The local pgvector index may store normalized chunks and embeddings in
`cce_control` for MVP proof. It is not a domain package store, a governance
store, a long-term graph store or a bypass around the approved-context runtime.

The SDK-backed adapter implements vector index, search and per-memory delete.
Graph/entity extraction remains unimplemented and disabled during writes.
Although adapter search is available, the governed runtime read path and
context assembly remain separate work and are not made complete by this ADR.
