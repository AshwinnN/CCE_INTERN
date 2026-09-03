# Ingestion Pipeline — Implementation Checklist & File Changes

## Phase 1: Core Workflow (Week 1)

### Files to Create

#### 1. `agents/ingestion_workflow.py` (350 lines)
**Status:** NEW

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Optional

class IngestionState(TypedDict):
    # See full design doc for complete fields

def route_by_source(state) → state
def fetch_unstructured(state) → state
def fetch_structured(state) → state
def parse_document(state) → state
def normalize_document(state) → state
def classify_for_dlp(state) → state
def redact_if_needed(state) → state
def emit_to_sdk(state) → state
def checkpoint(state) → state

def build_ingestion_workflow() → CompiledGraph
def run_ingestion(...) → (success, state)
```

**Dependencies:** None new (langgraph already available)

---

#### 2. `common/tools/__init__.py` (10 lines)
**Status:** NEW
```python
from .dlp_classifier import classify_text, redact_text
from .source_connector import fetch_unstructured, fetch_structured
from .document_normalizer import normalize_to_canonical
from .checkpoint_manager import save_checkpoint, load_checkpoint
```

---

#### 3. `common/tools/dlp_classifier.py` (150 lines)
**Status:** NEW

**Responsibility:** Deterministic PII detection

```python
import re

PATTERNS = {
    "SSN": r"\d{3}-\d{2}-\d{4}",
    "EMAIL": r"[\w\.-]+@[\w\.-]+\.\w+",
    "PHONE": r"\+?1?\s*\(?[0-9]{3}\)?[\s-]?[0-9]{3}[\s-]?[0-9]{4}",
    "CREDIT_CARD": r"\b(?:\d[ -]*?){13,19}\b",
    "API_KEY": r"(?:api[_-]?key|secret|token|password)\s*=\s*[\w\-]{20,}",
}

def classify_text(text: str, column_name: str = None) -> dict:
    """
    Input: text chunk, optional column name
    Output: {
        "sensitivity": "PUBLIC" | "INTERNAL" | "PII",
        "patterns_found": ["SSN", "EMAIL", ...],
        "confidence": 0.7,
    }
    """
    found_patterns = []
    for name, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            found_patterns.append(name)
    
    column_risk = 0.0
    if column_name:
        if any(x in column_name.lower() for x in ["pii", "ssn", "email", "phone", "secret"]):
            column_risk = 0.9
    
    if "SSN" in found_patterns or "CREDIT_CARD" in found_patterns:
        sensitivity = "PII"
    elif found_patterns or column_risk > 0.5:
        sensitivity = "INTERNAL"
    else:
        sensitivity = "PUBLIC"
    
    return {
        "sensitivity": sensitivity,
        "patterns_found": found_patterns,
        "confidence": 0.9 if found_patterns else (0.6 if column_risk > 0 else 0.95),
    }

def redact_text(text: str) -> str:
    """Replace sensitive patterns with [REDACTED]"""
    redacted = text
    for pattern in [PATTERNS["SSN"], PATTERNS["CREDIT_CARD"], PATTERNS["API_KEY"]]:
        redacted = re.sub(pattern, "[REDACTED]", redacted)
    return redacted
```

**Test cases:**
- Input: "My SSN is 123-45-6789" → OUTPUT: sensitivity=PII, patterns=["SSN"]
- Input: "Contact me at john@example.com" → OUTPUT: sensitivity=PUBLIC
- Input: "database_pii_table" column name → OUTPUT: sensitivity=PII

---

#### 4. `common/tools/source_connector.py` (120 lines)
**Status:** NEW

**Responsibility:** Fetch raw content using proven connection

```python
import os
import tempfile
from azure.storage.blob import BlobServiceClient

def fetch_unstructured(adapter: str, connection_handle: dict, object_id: str) -> bytes:
    """
    Download raw file bytes from blob storage or document service.
    Uses the already-proven connection_handle (read-only validated).
    """
    if adapter == "azure-blob":
        conn_str = os.environ["CCE_AZURE_BLOB_CONNECTION_STRING"]
        container = os.environ["CCE_AZURE_BLOB_CONTAINER"]
        
        service = BlobServiceClient.from_connection_string(conn_str)
        container_client = service.get_container_client(container)
        blob_client = container_client.get_blob_client(object_id)
        
        return blob_client.download_blob().readall()
    
    elif adapter == "google-docs":
        # Use connection_handle's oauth token
        # from google.colab import auth
        # TODO: implement
        pass
    
    else:
        raise ValueError(f"Unsupported adapter: {adapter}")

def fetch_structured(adapter: str, connection_handle: dict, schema: str = None) -> dict:
    """
    For structured sources: fetch schema + 1 sample row.
    Returns schema card ready for normalization.
    """
    if adapter == "snowflake":
        import snowflake.connector
        
        conn = connection_handle.get("_snowflake_connection")
        if not conn:
            raise ValueError("No Snowflake connection in handle")
        
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
        """, (schema,))
        
        schema_rows = cursor.fetchall()
        # Convert to CanonicalDocument shape
        return {
            "metadata": {"schema": schema, "source": "snowflake"},
            "elements": schema_rows,  # TODO: proper conversion
        }
    
    else:
        raise ValueError(f"Unsupported adapter: {adapter}")
```

---

#### 5. `common/tools/document_normalizer.py` (80 lines)
**Status:** NEW

**Responsibility:** Convert any parser output to canonical shape

```python
def normalize_to_canonical(parsed: dict, adapter: str) -> dict:
    """
    Normalize parsed content to CanonicalDocument.
    For unstructured: parsers already return this shape.
    For structured: convert schema card.
    """
    if adapter in ["azure-blob", "google-docs"]:
        # Parsed is already CanonicalDocument from parser
        return parsed
    
    elif adapter == "snowflake":
        # Convert schema rows to blocks
        return {
            "metadata": parsed.get("metadata"),
            "elements": [
                {
                    "type": "table",
                    "id": f"schema_{i}",
                    "text": f"{row[0]}.{row[1]} ({row[2]})",
                }
                for i, row in enumerate(parsed.get("elements", []))
            ]
        }
    
    return parsed
```

---

#### 6. `common/tools/checkpoint_manager.py` (100 lines)
**Status:** NEW

**Responsibility:** Persist ingestion state for resumption

```python
import json
import os
from typing import Optional, Dict

class CheckpointStore:
    def __init__(self, store_path: str = ".ingestion_checkpoints"):
        self.store_path = store_path
        os.makedirs(store_path, exist_ok=True)
    
    def save(self, source_id: str, object_id: str, state: dict) -> str:
        """Save checkpoint, return checkpoint_id"""
        checkpoint_id = f"{source_id}_{object_id}"
        path = os.path.join(self.store_path, f"{checkpoint_id}.json")
        
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
        
        return checkpoint_id
    
    def load(self, source_id: str, object_id: str) -> Optional[dict]:
        """Load previous checkpoint, return None if not found"""
        checkpoint_id = f"{source_id}_{object_id}"
        path = os.path.join(self.store_path, f"{checkpoint_id}.json")
        
        if not os.path.exists(path):
            return None
        
        with open(path, "r") as f:
            return json.load(f)
    
    def mark_complete(self, source_id: str, object_id: str, revision: str):
        """Mark as successfully processed"""
        self.save(
            source_id,
            object_id,
            {"status": "complete", "revision": revision}
        )

# Global instance (can be replaced with DB later)
_checkpoint_store = CheckpointStore()

def get_checkpoint_store() -> CheckpointStore:
    return _checkpoint_store
```

---

### Files to Modify

#### 7. `agents/connector_agent/agent.py` (MODIFY)
**Current:** Stops after connection is READY

**Change:** After connection + observation, trigger ingestion workflow

```python
# In ConnectorAgent.handle(), after the observation block:

if status == "connected" and mode == "start" and events:
    # NEW: trigger ingestion for each change event
    from agents.ingestion_workflow import run_ingestion
    
    ingestion_results = []
    for event in events:
        success, state = run_ingestion(
            change_event=event,
            source_id=descriptor["source_id"],
            adapter=descriptor["adapter"],
            kind=descriptor["kind"],
            connection_handle=handle,
            trace_id=trace_id,
        )
        ingestion_results.append({
            "object_id": event["object_id"],
            "success": success,
            "checkpoint_id": state.get("checkpoint_id"),
            "errors": state.get("errors", []),
        })
    
    # Extend response to include ingestion results
    return ConnectorResponse(
        ...existing fields...,
        ingestion_results=ingestion_results,  # NEW FIELD
    )
```

---

#### 8. `agents/connector_agent/contracts.py` (MODIFY)
**Current:** ConnectorResponse has no ingestion_results field

**Change:** Add optional ingestion_results

```python
class ConnectorResponse(BaseModel):
    ...existing fields...
    ingestion_results: Optional[List[dict]] = None  # NEW
```

---

#### 9. `.env` (ADD VARS)
**Status:** UPDATE

```bash
# Ingestion behavior
CCE_INGESTION_MODE=stream           # stream | batch | disabled
CCE_DLP_CONFIDENCE_THRESHOLD=0.7    # Only redact if confidence >= this
CCE_SDK_ENDPOINT=http://localhost:8000/ingest  # Your SDK's ingestion endpoint
CCE_SDK_API_KEY=your-key-here       # Authorization for SDK endpoint
CCE_CHECKPOINT_STORE_PATH=.ingestion_checkpoints  # Where to store resumption state
```

---

### Tests to Add

#### 10. `tests/test_dlp_classifier.py` (NEW, 60 lines)
```python
from common.tools.dlp_classifier import classify_text, redact_text

def test_ssn_detection():
    result = classify_text("My SSN is 123-45-6789")
    assert result["sensitivity"] == "PII"
    assert "SSN" in result["patterns_found"]

def test_email_detection():
    result = classify_text("Email me at john@example.com")
    assert result["sensitivity"] == "PUBLIC"
    assert "EMAIL" in result["patterns_found"]

def test_column_name_risk():
    result = classify_text("normal text", column_name="customer_pii_id")
    assert result["sensitivity"] == "PII"

def test_redaction():
    text = "SSN: 123-45-6789, CC: 4532-1111-2222-3333"
    redacted = redact_text(text)
    assert "[REDACTED]" in redacted
    assert "123-45-6789" not in redacted
```

---

#### 11. `tests/test_ingestion_workflow.py` (NEW, 150 lines)
```python
from agents.ingestion_workflow import (
    IngestionState, build_ingestion_workflow, run_ingestion
)

def test_route_unstructured():
    state = IngestionState(kind="unstructured", ...)
    from agents.ingestion_workflow import route_by_source
    result = route_by_source(state)
    assert result["_next_node"] == "fetch_unstructured"

def test_route_structured():
    state = IngestionState(kind="structured", ...)
    result = route_by_source(state)
    assert result["_next_node"] == "fetch_structured"

def test_full_workflow_unstructured():
    # Mock file in temp location
    # Run full workflow
    # Assert ready_for_sdk=True
    pass

def test_full_workflow_with_dlp():
    # Input document with PII
    # Run workflow
    # Assert dlp_verdict.sensitivity="PII"
    # Assert redacted_text contains [REDACTED]
    pass
```

---

## Phase 2: SDK Integration (Week 2)

### Modify `emit_to_sdk` Node
```python
def emit_to_sdk(state: IngestionState) -> IngestionState:
    """Hand off to your SDK"""
    try:
        import requests
        
        payload = {
            "document_id": state["change_event"]["object_id"],
            "source_id": state["source_id"],
            "revision": state["change_event"]["revision"],
            "text": state["redacted_text"],
            "blocks": state["redacted_text"].get("elements", []),
            "dlp_verdict": state["dlp_verdict"],
            "trace_id": state["trace_id"],
        }
        
        # Call your SDK
        response = requests.post(
            os.environ["CCE_SDK_ENDPOINT"],
            json=payload,
            headers={"Authorization": f"Bearer {os.environ['CCE_SDK_API_KEY']}"},
            timeout=30,
        )
        
        if response.status_code == 200:
            result = response.json()
            state["memory_id"] = result.get("memory_id")
            state["chunks_count"] = result.get("chunks_count")
        else:
            state["errors"].append(f"SDK rejected: {response.status_code}")
    
    except Exception as e:
        state["errors"].append(f"emit_to_sdk: {str(e)}")
    
    return state
```

---

## Execution Order (Do in this sequence)

```
1. Create common/tools/ package with 5 modules
   └─ Validate each tool independently with unit tests
   
2. Create agents/ingestion_workflow.py
   └─ Build the graph
   └─ Test each node in isolation
   
3. Create tests/ for workflow
   └─ Test full workflow end-to-end with fixtures
   
4. Modify agents/connector_agent/agent.py
   └─ Wire ingestion into observation callback
   └─ Test Connectors → Ingestion → SDK flow
   
5. Update .env
   └─ Add all new variables with defaults
   
6. Integration test:
   └─ Run full flow: connect → observe → ingest → SDK
   └─ Verify checkpoint store has records
   └─ Verify SDK received payload
```

---

## Key Points (Read This)

1. **NO SKILLS in the ingestion path** — skills remain as documentation and future governance gates. Ingestion is pure execution.

2. **LangGraph owns the sequence** — every node is explicit, state flows through cleanly, no implicit dependencies.

3. **Deterministic tools only** — no ML, no external services. Same input → same output, always.

4. **Checkpoint for resumption** — if a node fails midway, you can resume from where it stopped.

5. **Clear hand-off to SDK** — structured payload, trace_id carries through for debugging.

6. **Test-first** — write test cases before implementation; makes implementation trivial.

---

## Deployment Readiness Checklist

- [ ] All 5 tools created and unit-tested
- [ ] Ingestion workflow graph built and tested
- [ ] Connectors → Ingestion integration tested
- [ ] Checkpoint store working (can save/load)
- [ ] SDK endpoint integration tested
- [ ] Trace IDs flow through entire pipeline
- [ ] Error handling at each node (no silent failures)
- [ ] .env has all required variables
- [ ] Logging structured (JSON lines, not print statements)
- [ ] README updated with ingestion flow
