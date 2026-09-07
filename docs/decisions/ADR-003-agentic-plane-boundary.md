# ADR-003: AgenticPlane Boundary

CCE consumes AgenticPlane through `cce.integrations.agentic_plane` and does
not depend on AgenticPlane storage or infrastructure internals.

## Status

Accepted. The production vector and graph adapter is SDK-backed; the local
implementation remains available for offline and developer testing.

## Decision

CCE code outside `cce.integrations.agentic_plane` depends on a small boundary:
index, search, delete and graph operations. Production AgenticPlane integration
lives in `AgenticPlaneClient`. It sends raw chunk text to AgenticPlane for
server-side embedding and records only the returned memory references in CCE's
`cce_agentic_plane_memory` bridge table. AgenticPlane owns chunk text and
vectors plus graph entities/relationships; CCE owns references, source
provenance, governance, approvals and audit state.

After each batch memory write, CCE invokes synchronous, per-memory
`graph.extract_and_store()` with the raw chunk and returned memory ID. This
keeps entity source links deterministic when ingestion completes and does not
enable the SDK's asynchronous NATS extraction flag. GraphRAG reads likewise
remain behind `AgenticPlaneClient.graph()`.

`LocalIndexClient` provides a pgvector-backed implementation behind the same
boundary for offline use. Both implementations share payload chunking and
expose cosine-similarity scores where higher is better. This keeps
server-triggered ingestion searchable without creating a second ingestion or
retrieval architecture.

The separate raw `RetrievalService` and its `/retrieve` HTTP and gRPC adapters
consume only this boundary. They are an infrastructure proof, not the governed
`QueryService` runtime. `LocalIndexClient.graph()` raises
`GraphNotSupportedError`; raw retrieval preserves local memory results and
maps that exception to an explicit unsupported graph block.

## Consequences

The local pgvector index may store normalized chunks and embeddings in
`cce_control` for MVP proof. It is not a domain package store, a governance
store, a long-term graph store or a bypass around the approved-context runtime.

The SDK-backed adapter implements memory index/search/per-memory delete,
synchronous graph extraction and GraphRAG search. Hosted graph operations
require `GRAPH_ENABLED=true` and a running ArcadeDB service (the AgenticPlane
`graph` Compose profile); failures are surfaced as ingestion errors rather
than empty successes. The governed runtime read path, context assembly,
governance and packages remain separate work and are not made complete by this
ADR.
