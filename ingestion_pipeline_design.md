# CCE Ingestion Pipeline — LangGraph Workflow & Tool Architecture
## Changes Needed, Flow Diagram, and Responsibilities

---

## Current State vs Target

### What you have now:
- **Connectors Agent** (orchestrator.py) — chains skills for registry → credential → connect
- **Ingestion module** (parsers, azure_blob_source) — document parsing to canonical model
- **Skills** (document-content-extraction, chunking, etc.) — exist but aren't wired into a working pipeline

### What you need:
- **Remove skills from the ingestion path** — they were designed as governance gates, but you don't need governance here yet, you need execution
- **Build a LangGraph workflow** — stateful, checkpointable, with clear state transitions
- **Deterministic tools** — no agents making judgment calls on what to do next; every step is predetermined
- **Clear hand-off to your SDK** — ingest outputs metadata + references, SDK does chunking/embedding/memory

---

## The Three Layers (New Architecture)

```
┌─────────────────────────────────────────────────────────────────┐
│ CONNECTORS AGENT (existing, unchanged)                          │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ registry → credential → connect → observation.mode=start   │  │
│ │ Output: connection_handle, change events (added/changed)   │  │
│ └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ INGESTION WORKFLOW (NEW: LangGraph-based)                       │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ Input: change events from Connectors                       │  │
│ │ State: {event, parsed_doc, normalized, classified, ready}  │  │
│ │ Nodes:                                                      │  │
│ │  1. route_by_source() → unstructured vs structured         │  │
│ │  2. fetch_object() → download/query raw content            │  │
│ │  3. parse() → detect MIME, parse to CanonicalDocument      │  │
│ │  4. normalize() → convert to canonical blocks              │  │
│ │  5. classify_for_dlp() → heuristic PII/sensitivity         │  │
│ │  6. redact_if_needed() → replace patterns                  │  │
│ │  7. emit_to_sdk() → hand off to chunking/embedding SDK     │  │
│ │  8. checkpoint() → store processed state                   │  │
│ │                                                             │  │
│ │ Paths:                                                      │  │
│ │  - success → emit → checkpoint → next event                │  │
│ │  - parse_fail → log error → checkpoint → next event        │  │
│ │  - dlp_reject → log & skip → checkpoint → next event       │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ Output: (document, metadata, classification, redacted_text)    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ YOUR SDK (chunking, embedding, memory)                          │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ Input: (document, metadata, classification, text)         │  │
│ │ Output: (chunks[], embeddings[], memory_store_id)         │  │
│ └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## LangGraph Workflow Definition

```python
# agents/ingestion_workflow.py

from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Optional
from dataclasses import dataclass, field

# ===== STATE SHAPE =====

class IngestionState(TypedDict):
    """The full state flowing through the workflow."""
    # Input from Connectors
    source_id: str                    # "snowflake-prod" or "azure-blob-contracts"
    adapter: str                      # "snowflake" or "azure-blob"
    kind: str                         # "structured" or "unstructured"
    connection_handle: dict           # From Connectors Agent
    change_event: dict                # {object_id, revision, state: "added"/"changed", ...}
    
    # Intermediate results
    raw_content: Optional[bytes] = None
    raw_text: Optional[str] = None
    parsed_doc: Optional[dict] = None     # CanonicalDocument shape
    normalized_doc: Optional[dict] = None
    
    # Classification & redaction
    dlp_verdict: Optional[dict] = None    # {sensitivity, patterns, redacted_text, confidence}
    redacted_text: Optional[str] = None
    
    # Errors & metadata
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    processing_duration_ms: Optional[float] = None
    
    # Output ready for SDK
    ready_for_sdk: bool = False
    
    # Checkpoint
    trace_id: str = ""
    checkpoint_id: Optional[str] = None

# ===== WORKFLOW NODES =====

def route_by_source(state: IngestionState) -> IngestionState:
    """
    Deterministic router: read state.kind and set next node path.
    This is where the single fork lives — everything else flows through.
    """
    if state.kind == "structured":
        state["_next_node"] = "fetch_structured"
    else:
        state["_next_node"] = "fetch_unstructured"
    return state

def fetch_unstructured(state: IngestionState) -> IngestionState:
    """
    Download raw bytes from the unstructured source
    (Azure Blob, Google Docs, etc.) using the connection handle.
    """
    try:
        adapter = state["adapter"]
        obj_id = state["change_event"]["object_id"]
        
        if adapter == "azure-blob":
            from ingestion.azure_blob_source import AzureBlobSource
            source = AzureBlobSource(
                connection_string=os.environ["CCE_AZURE_BLOB_CONNECTION_STRING"],
                container_name=os.environ["CCE_AZURE_BLOB_CONTAINER"],
            )
            blob_client = source.container_client.get_blob_client(obj_id)
            raw = blob_client.download_blob().readall()
            state["raw_content"] = raw
        # elif adapter == "google-docs": ...
        
        return state
    except Exception as e:
        state["errors"].append(f"fetch_unstructured: {str(e)}")
        return state

def fetch_structured(state: IngestionState) -> IngestionState:
    """
    For structured sources: fetch a small sample of data
    (schema card, not entire table). Use the connection_handle
    to query the database, fetch schema + 1 sample row.
    """
    # This is delegated to skill-schema-discovery via a tool call
    # since it needs SQL guard, dialect profile, etc.
    # For now: stub it as "return what the connection handle has cached"
    state["raw_content"] = state["connection_handle"].get("cached_schema_card")
    return state

def parse_document(state: IngestionState) -> IngestionState:
    """
    Unstructured only: parse raw bytes into CanonicalDocument
    (the Canonical model your ingestion/models.py already defines).
    Uses ParserFactory to dispatch by MIME type.
    """
    if state["kind"] != "unstructured" or not state["raw_content"]:
        return state
    
    try:
        from ingestion.parsers.factory import ParserFactory
        from ingestion.file_detection import detect_mime_type
        import tempfile
        import os
        
        # Write to temp file for parser
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp") as tmp:
            tmp.write(state["raw_content"])
            tmp_path = tmp.name
        
        # Detect MIME
        mime_type = detect_mime_type(tmp_path)
        
        # Get parser
        parser = ParserFactory.get_parser(mime_type)
        if not parser:
            state["errors"].append(f"Unsupported MIME type: {mime_type}")
            return state
        
        # Parse to CanonicalDocument
        from ingestion.models import DocumentMetadata
        doc_metadata = DocumentMetadata(
            document_id=state["change_event"]["object_id"],
            source_system=state["adapter"],
            source_uri=state["change_event"].get("source_uri"),
            mime_type=mime_type,
        )
        
        result = parser.parse(tmp_path, doc_metadata)  # Returns ProcessingResult
        if result.status.value == "SUCCESS":
            state["parsed_doc"] = result.document.dict()
        else:
            state["errors"].extend(result.errors)
        
        os.remove(tmp_path)
    except Exception as e:
        state["errors"].append(f"parse_document: {str(e)}")
    
    return state

def normalize_document(state: IngestionState) -> IngestionState:
    """
    Convert parsed document to normalized shape (CanonicalDocument with
    identical block types: prose, table, code, procedure, log, key_value).
    For structured sources: schema card is already normalized.
    For unstructured: convert parser output to blocks.
    """
    if not state["parsed_doc"] and state["kind"] == "unstructured":
        return state
    
    try:
        # For unstructured, parsed_doc IS already in CanonicalDocument shape
        # (your ingestion models already do this).
        # For structured, schema_card is the normalized form.
        state["normalized_doc"] = state["parsed_doc"]
        return state
    except Exception as e:
        state["errors"].append(f"normalize_document: {str(e)}")
        return state

def classify_for_dlp(state: IngestionState) -> IngestionState:
    """
    Deterministic PII/sensitivity classification using heuristic patterns.
    Calls tools/dlp_classifier.py for every text block.
    """
    if not state["normalized_doc"]:
        return state
    
    try:
        from common.tools.dlp_classifier import classify_text
        
        doc = state["normalized_doc"]
        dlp_results = []
        
        for block in doc.get("elements", []):
            if block.get("type") in ["text", "prose", "paragraph"]:
                text = block.get("text", "")
                result = classify_text(text)
                dlp_results.append({
                    "block_id": block.get("id"),
                    "sensitivity": result["sensitivity"],
                    "patterns_found": result["patterns_found"],
                    "confidence": result["confidence"],
                })
        
        # Aggregate: if ANY block is PII, whole document is flagged
        max_sensitivity = max(
            (r["sensitivity"] for r in dlp_results),
            default="PUBLIC"
        )
        state["dlp_verdict"] = {
            "sensitivity": max_sensitivity,
            "block_verdicts": dlp_results,
        }
    except Exception as e:
        state["errors"].append(f"classify_for_dlp: {str(e)}")
        state["dlp_verdict"] = {"sensitivity": "INTERNAL", "block_verdicts": []}
    
    return state

def redact_if_needed(state: IngestionState) -> IngestionState:
    """
    If classification flagged PII patterns, redact them.
    Otherwise pass through unchanged.
    """
    if not state["dlp_verdict"]:
        state["redacted_text"] = state["normalized_doc"]
        return state
    
    try:
        from common.tools.dlp_classifier import redact_text
        
        doc = state["normalized_doc"]
        
        for block in doc.get("elements", []):
            if block.get("type") in ["text", "prose", "paragraph"]:
                verdict = next(
                    (v for v in state["dlp_verdict"]["block_verdicts"]
                     if v["block_id"] == block.get("id")),
                    None
                )
                if verdict and verdict["sensitivity"] in ["PII", "INTERNAL"]:
                    block["text"] = redact_text(block["text"])
        
        state["redacted_text"] = doc
    except Exception as e:
        state["errors"].append(f"redact_if_needed: {str(e)}")
        state["redacted_text"] = state["normalized_doc"]
    
    return state

def emit_to_sdk(state: IngestionState) -> IngestionState:
    """
    Package the classified, redacted document as a hand-off to the SDK
    for chunking, embedding, memory management.
    
    Output format:
    {
        "document_id": str,
        "source_id": str,
        "revision": str,
        "metadata": {...},
        "text": str (redacted if needed),
        "blocks": [...],  (CanonicalDocument.elements)
        "dlp_verdict": {...},
        "source_reference": str,
    }
    """
    try:
        payload = {
            "document_id": state["change_event"]["object_id"],
            "source_id": state["source_id"],
            "revision": state["change_event"]["revision"],
            "adapter": state["adapter"],
            "kind": state["kind"],
            "metadata": state["normalized_doc"].get("metadata") if state["normalized_doc"] else {},
            "text": state["redacted_text"].get("metadata", {}).get("text") if state["redacted_text"] else None,
            "blocks": state["redacted_text"].get("elements", []) if state["redacted_text"] else [],
            "dlp_verdict": state["dlp_verdict"],
            "trace_id": state["trace_id"],
        }
        
        # TODO: Call your SDK's ingest endpoint here
        # sdk_client.ingest(payload)
        
        state["ready_for_sdk"] = True
    except Exception as e:
        state["errors"].append(f"emit_to_sdk: {str(e)}")
        state["ready_for_sdk"] = False
    
    return state

def checkpoint(state: IngestionState) -> IngestionState:
    """
    Store the processed state in a durable checkpoint store.
    Allows resumption if the workflow is interrupted.
    """
    try:
        from common.checkpoint_store import get_checkpoint_store
        store = get_checkpoint_store()
        
        checkpoint_data = {
            "source_id": state["source_id"],
            "object_id": state["change_event"]["object_id"],
            "revision": state["change_event"]["revision"],
            "status": "success" if not state["errors"] else "partial",
            "errors": state["errors"],
            "warnings": state["warnings"],
            "ready_for_sdk": state["ready_for_sdk"],
            "trace_id": state["trace_id"],
        }
        
        checkpoint_id = store.set(state["source_id"], checkpoint_data)
        state["checkpoint_id"] = checkpoint_id
    except Exception as e:
        state["warnings"].append(f"checkpoint failed: {str(e)}")
    
    return state

# ===== BUILD THE GRAPH =====

def build_ingestion_workflow():
    workflow = StateGraph(IngestionState)
    
    # Add nodes
    workflow.add_node("route", route_by_source)
    workflow.add_node("fetch_unstructured", fetch_unstructured)
    workflow.add_node("fetch_structured", fetch_structured)
    workflow.add_node("parse", parse_document)
    workflow.add_node("normalize", normalize_document)
    workflow.add_node("classify_dlp", classify_for_dlp)
    workflow.add_node("redact", redact_if_needed)
    workflow.add_node("emit", emit_to_sdk)
    workflow.add_node("checkpoint", checkpoint)
    
    # Add edges
    workflow.set_entry_point("route")
    
    # Conditional: route splits by kind
    def route_conditional(state):
        return state.get("_next_node", "fetch_unstructured")
    
    workflow.add_conditional_edges(
        "route",
        route_conditional,
        {
            "fetch_unstructured": "fetch_unstructured",
            "fetch_structured": "fetch_structured",
        }
    )
    
    # Unstructured path
    workflow.add_edge("fetch_unstructured", "parse")
    workflow.add_edge("parse", "normalize")
    
    # Structured path
    workflow.add_edge("fetch_structured", "normalize")
    
    # Converge
    workflow.add_edge("normalize", "classify_dlp")
    workflow.add_edge("classify_dlp", "redact")
    workflow.add_edge("redact", "emit")
    workflow.add_edge("emit", "checkpoint")
    workflow.add_edge("checkpoint", END)
    
    return workflow.compile()

# ===== INVOCATION =====

def run_ingestion(change_event: dict, source_id: str, adapter: str, kind: str,
                  connection_handle: dict, trace_id: str):
    """
    Entry point: given a single change event from the Connectors Agent,
    run it through the full ingestion workflow.
    
    Returns: (success: bool, state: IngestionState)
    """
    workflow = build_ingestion_workflow()
    
    initial_state = IngestionState(
        source_id=source_id,
        adapter=adapter,
        kind=kind,
        connection_handle=connection_handle,
        change_event=change_event,
        trace_id=trace_id,
    )
    
    final_state = workflow.invoke(initial_state)
    
    return (len(final_state["errors"]) == 0, final_state)
```

---

## Tools and Responsibilities

Create `common/tools/` with these modules:

### 1. **`tools/dlp_classifier.py`** — PII detection & redaction
```python
# Deterministic regex + heuristic-based classification
# NO ML, NO external API

def classify_text(text: str, column_name: str = None) -> dict:
    """
    Returns: {
        "sensitivity": "PUBLIC" | "INTERNAL" | "PII",
        "patterns_found": ["SSN", "EMAIL", "API_KEY"],
        "confidence": 0.0-1.0,
    }
    """
    # Patterns:
    # - SSN: \d{3}-\d{2}-\d{4}
    # - EMAIL: [\w\.-]+@[\w\.-]+\.\w+
    # - PHONE: \+?1?\s*\(?[0-9]{3}\)?
    # - CREDIT_CARD: \b(?:\d[ -]*?){13,19}\b
    # - API_KEY: (api|secret|token|password)\s*=\s*[\w\-]{20,}
    
    # Column name risk:
    # - If *_pii or sensitive_* or secret_* → high risk

def redact_text(text: str) -> str:
    """Replace patterns with [REDACTED]"""
    # Apply regex substitutions for SSN, CC, API keys
```

### 2. **`tools/source_connector.py`** — Fetch raw content
```python
def fetch_unstructured(adapter: str, connection_handle: dict, object_id: str) -> bytes:
    """Download raw file from blob/drive/etc."""
    # Dispatch on adapter type
    # Use connection_handle (already proven read-only)
    
def fetch_structured(adapter: str, connection_handle: dict) -> dict:
    """Fetch schema + 1 sample row from warehouse"""
    # Query system catalog + sample row
    # Return schema card
```

### 3. **`tools/document_normalizer.py`** — Convert parser output
```python
def normalize_to_canonical(parsed: dict, adapter: str) -> dict:
    """
    Convert any parser output to CanonicalDocument shape.
    For unstructured: your parsers already do this.
    For structured: convert schema card to blocks.
    """
```

### 4. **`tools/change_detector.py`** — Determine what changed (from Connectors)
```python
def extract_change_events(manifest: dict) -> List[dict]:
    """
    Parse skill-source-sync's delta manifest into individual events.
    Returns list of {object_id, revision, state: "added"/"changed"/"deleted"}
    """
```

### 5. **`tools/checkpoint_manager.py`** — Store and retrieve ingestion state
```python
def save_checkpoint(source_id: str, object_id: str, state: dict) -> str:
    """Store in-progress state; return checkpoint_id for resumption"""

def load_checkpoint(source_id: str, object_id: str) -> Optional[dict]:
    """Retrieve prior state for resumption"""

def mark_complete(source_id: str, object_id: str, revision: str):
    """Mark as successfully processed, store final revision"""
```

---

## High-Level Flow: Connectors → Ingestion → Your SDK

```
┌──────────────────────────────────┐
│ CONNECTORS AGENT                 │
│ .handle(ConnectorRequest)        │
│  - registry ✅                   │
│  - credential ✅                 │
│  - connect ✅                    │
│  - observation.mode="start"      │
└────────────────────┬─────────────┘
                     │
                     │ Returns:
                     │ {
                     │   status: "connected",
                     │   observation_handle: "obs_123",
                     │   change_events: [
                     │     {object_id, revision, state}
                     │   ]
                     │ }
                     ↓
        ┌────────────────────────────┐
        │ FOR EACH change_event:     │
        │                            │
        │ run_ingestion(             │
        │   event,                   │
        │   source_id,               │
        │   adapter,                 │
        │   kind,                    │
        │   connection_handle,       │
        │   trace_id                 │
        │ )                          │
        └────────────────────────────┘
                     │
                     ↓
        ┌────────────────────────────┐
        │ INGESTION WORKFLOW         │
        │ (LangGraph)                │
        │                            │
        │ route →                    │
        │ fetch →                    │
        │ parse →                    │
        │ normalize →                │
        │ classify_dlp →             │
        │ redact →                   │
        │ emit →                     │
        │ checkpoint                 │
        └────────────────────────────┘
                     │
                     │ Emits to SDK:
                     │ {
                     │   document_id,
                     │   source_id,
                     │   text (redacted),
                     │   blocks (normalized),
                     │   dlp_verdict,
                     │   trace_id
                     │ }
                     ↓
        ┌────────────────────────────┐
        │ YOUR SDK                   │
        │ .ingest(payload)           │
        │                            │
        │ - Chunk                    │
        │ - Embed                    │
        │ - Store in memory          │
        │ - Return memory_id         │
        └────────────────────────────┘
```

---

## Changes to Make (File-by-file)

### 1. **Create `agents/ingestion_workflow.py`** (NEW)
Full LangGraph workflow as shown above.

### 2. **Create `common/tools/`** (NEW PACKAGE)
All five tool modules listed above.

### 3. **Refactor `agents/connector_agent/agent.py`**
Add a new mode: after connection is READY and observation starts, instead of returning immediately, call the ingestion workflow:

```python
# In ConnectorAgent.handle()

if status == "connected" and mode == "start":
    # Observation has already returned events
    from agents.ingestion_workflow import run_ingestion
    
    for event in connection["observation_handle"].get_events():
        success, state = run_ingestion(
            change_event=event,
            source_id=request.source_id,
            adapter=descriptor["adapter"],
            kind=descriptor["kind"],
            connection_handle=handle,
            trace_id=trace_id,
        )
        # Log state (errors, warnings, checkpoint_id)
```

### 4. **Update `.env`** (no new vars needed, but document)
```
# Ingestion behavior
CCE_INGESTION_MODE=stream           # stream | batch | disabled
CCE_DLP_CONFIDENCE_THRESHOLD=0.7    # Skip redaction below this confidence
CCE_SDK_ENDPOINT=http://localhost:8000/ingest  # Your SDK's ingest URL
```

### 5. **Create `tests/test_ingestion_workflow.py`** (NEW)
Test each node independently + integration tests:
```python
def test_route_unstructured():
    # Assert _next_node = "fetch_unstructured"

def test_classify_dlp():
    # Assert SSN pattern detected
    # Assert email pattern detected

def test_full_workflow():
    # End-to-end: blob → parse → classify → redact → emit
```

### 6. **No changes needed to:**
- `skills/Connect_Ingest_Ground/skill-*.md` — keep as reference documentation
- `ingestion/parsers/` — they're good as-is
- `ingestion/models.py` — CanonicalDocument is correct
- Connectors Agent (`agent.py`, `orchestrator.py`) — they stay as-is for the connection stage

---

## Responsibilities Summary

| Component | Responsibility | Owner |
|---|---|---|
| **Connectors Agent** | Get a safe, guarded connection to the source | Orchestrator (skill-driven) |
| **IngestionWorkflow** | Process each change event through normalized pipeline | LangGraph state machine |
| **dlp_classifier tool** | Identify PII/sensitivity patterns, suggest redaction | Deterministic rules |
| **source_connector tool** | Fetch raw content using proven connection | Deterministic fetch |
| **document_normalizer tool** | Convert parser output to canonical shape | Deterministic mapping |
| **checkpoint_manager tool** | Persist and resume state | Deterministic storage |
| **Your SDK** | Chunk, embed, store in memory, return IDs | Your responsibility |

---

## Why This Design

1. **LangGraph owns the sequence** — not skills, not agents. Clear state flow, checkpointable, debuggable.
2. **Deterministic tools** — no ML, no guessing. Same input = same output. Fast iteration.
3. **No agentic judgment** — the workflow is pre-determined. Every decision point is explicit.
4. **Clear hand-off** — ingestion ends, SDK begins. Payload is structured, trace_id carries through.
5. **Fits your architecture** — skills remain as governance gates (Phase 2). Ingestion is execution (Phase 1).

---

## Next: Implementation Checklist

- [ ] Create `agents/ingestion_workflow.py` with the full graph
- [ ] Create `common/tools/dlp_classifier.py` with regex patterns
- [ ] Create `common/tools/source_connector.py` with fetch logic
- [ ] Create remaining tools (normalizer, change detector, checkpoint)
- [ ] Add ingestion callback to `agents/connector_agent/agent.py`
- [ ] Write integration tests
- [ ] Wire your SDK's endpoint into `emit_to_sdk()` node
- [ ] Document the payload format your SDK expects
