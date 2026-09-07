# External Integrations Guide

## Status

**PARTIAL**

Implemented:
- Gemini wrapper using `ChatGoogleGenerativeAI`, deterministic temperature 0.
- explicit AgenticPlane package boundary.
- SDK-backed AgenticPlane index/search/delete with CCE-owned memory references.
- pgvector local fallback using the same payload chunking and search shape.

Missing / incomplete:
- no production caller uses the Gemini wrapper;
- the governed runtime read/context-assembly path is not wired;
- AgenticPlane graph/entity extraction is not implemented.

## Purpose

Isolate third-party model/platform SDKs so core CCE modules do not depend on their infrastructure internals.

## Does NOT Own

- CCE governance or package rules
- prompt/business domain content
- storage schemas owned by CCE
- transport logic

## Entry Points

- `backend/src/cce/integrations/llm/client.py::complete()`
- `backend/src/cce/integrations/agentic_plane/client.py::AgenticPlaneClient.index()`
- `backend/src/cce/integrations/agentic_plane/client.py::AgenticPlaneClient.search()`
- `backend/src/cce/integrations/agentic_plane/client.py::AgenticPlaneClient.delete()`

## Main Flow

Current LLM:

```text
complete(prompt)
  -> requires CCE_LLM_API_KEY
  -> ChatGoogleGenerativeAI(model=CCE_LLM_MODEL, temperature=0)
  -> message content
```

Current AgenticPlane write path:

```text
normalized payload
  -> shared block/cell chunking
  -> SDK memory.store_batch(raw text)
  -> cce_agentic_plane_memory references
```

## Important Components

`integrations/llm/client.py`
- `DEFAULT_MODEL = "gemini-2.5-flash"`.
- `complete()` creates the model client per call and returns message content.

`integrations/agentic_plane/client.py`
- `AgenticPlaneClient` wraps SDK memory index/search/per-memory delete.
- graph operations remain intentionally unimplemented.

## Inputs / Outputs

Inputs:
- LLM prompt / response format.
- retrieval question.

Outputs:
- LLM text response.
- backend-neutral retrieval/search results with provenance.

## Dependencies

- `langchain-google-genai`
- AgenticPlane Python SDK
- private package-registry pip configuration for container builds
- CCE control Postgres for the memory-reference bridge

## Used By

- `SourceService` injects the configured boundary into ingestion writes.
- `runtime/retrieval.py` retains a legacy adapter-specific seam; the governed
  runtime read path is not active.
- Gemini wrapper has no production call site found; tests exercise it.

## Invariants

### Enforced

- LLM temperature is fixed to 0 in this wrapper.
- AgenticPlane has an explicit integration package boundary (ADR-003).

### Architectural Requirements — PARTIAL

- all AgenticPlane storage/retrieval interaction must stay behind this adapter;
- agentic CCE reasoning should invoke an approved/pinned LLM path, but runtime is not implemented;
- external retrieval must respect approved-only/entitlement filters; no such call exists yet.

## Modification Guide

Implement external SDK calls here and expose CCE-side typed methods. Do not leak provider SDK types across runtime/governance interfaces.

## Impact Map

| Change | Usually Modify | Potentially Impacted | Normally Unrelated |
|---|---|---|---|
| LLM provider/model | `integrations/llm/` | agent/runtime code that calls it | structured metadata |
| AgenticPlane retrieval | `agentic_plane/` | runtime retrieval, ingestion downstream integration | RPC serialization |

## Do Not Inspect Unless Needed

Skip provider connectors, migrations and frontend for a pure SDK adapter change.

## Known Gaps / Architecture Mismatch

Expected:
- AgenticPlane is the external vector/graph/retrieval boundary.

Current:
- source-service ingestion uses the configured SDK-backed or local boundary;
- runtime retrieval/context assembly and graph operations remain incomplete.

Status: **PARTIAL**
