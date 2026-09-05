# External Integrations Guide

## Status

**PARTIAL**

Implemented:
- Gemini wrapper using `ChatGoogleGenerativeAI`, deterministic temperature 0.
- explicit AgenticPlane package boundary.

Missing / incomplete:
- no production caller uses the Gemini wrapper;
- AgenticPlane retrieval always returns an empty list;
- no index/search/graph/delete implementation exists in this adapter.

## Purpose

Isolate third-party model/platform SDKs so core CCE modules do not depend on their infrastructure internals.

## Does NOT Own

- CCE governance or package rules
- prompt/business domain content
- storage schemas owned by CCE
- transport logic

## Entry Points

- `backend/src/cce/integrations/llm/client.py::complete()`
- `backend/src/cce/integrations/agentic_plane/client.py::AgenticPlaneClient.retrieve()`

## Main Flow

Current LLM:

```text
complete(prompt)
  -> requires CCE_LLM_API_KEY
  -> ChatGoogleGenerativeAI(model=CCE_LLM_MODEL, temperature=0)
  -> message content
```

Current AgenticPlane:

```text
retrieve(question) -> []
```

## Important Components

`integrations/llm/client.py`
- `DEFAULT_MODEL = "gemini-2.5-flash"`.
- `complete()` creates the model client per call and returns message content.

`integrations/agentic_plane/client.py`
- `AgenticPlaneClient` boundary; current `retrieve()` is a stub.

## Inputs / Outputs

Inputs:
- LLM prompt / response format.
- retrieval question.

Outputs:
- LLM text response.
- currently empty AgenticPlane retrieval list.

## Dependencies

- `langchain-google-genai`
- target external AgenticPlane SDK (not meaningfully used in current client)

## Used By

- `runtime/retrieval.py` instantiates/calls AgenticPlane retrieval boundary.
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
- adapter implements only `retrieve()` and returns `[]`; ingestion instead uses a generic `CCE_SDK_ENDPOINT` HTTP emit helper.

Status: **PARTIAL**
