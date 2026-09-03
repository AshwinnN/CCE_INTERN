# Ingestion Pipeline — Executive Summary

You have two production documents now:

1. **`ingestion_pipeline_design.md`** — Complete LangGraph workflow code + architecture rationale
2. **`ingestion_implementation_checklist.md`** — File-by-file changes, what to create, what to modify, test cases

**Read this summary first, then dive into those two documents in order.**

---

## The 30-Second Version

**What you have:**
- Connectors stage (100% done) — connects to Snowflake/Azure Blob, proves read-only
- Ingestion parsers — convert PDFs/docs to a canonical shape
- Skills library — sits on the shelf, used for Phase 2 governance

**What you're building:**
- **LangGraph workflow** — deterministic state machine that processes each file through 9 nodes
- **5 tools** — all deterministic, no ML, no external APIs: DLP classifier, fetch, normalize, checkpoint, connector
- **Hand-off to your SDK** — structured JSON payload with trace_id, gets chunks/embeddings back

**Flow:** Connectors detects change → Ingestion workflow processes it → SDK chunks+embeds → ready for Phase 2 (governance/retrieval)

---

## The Architecture in One Picture

```
┌─────────────────────────────────────────────────────────────┐
│ CONNECTORS AGENT (existing, unchanged)                      │
│ Registry → Credential → Connect → Observe (change detection)│
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ "change_event": 
                     │   {object_id, revision, state, ...}
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ INGESTION WORKFLOW (LangGraph — new)                        │
│                                                              │
│ [Route] ────→ structured? ─┐                                │
│     │              └─→ unstructured? ──┐                    │
│     │                                  ↓                    │
│  unstructured                    [Fetch Structured]         │
│     ↓                                 │                     │
│ [Fetch Blob]                         │                     │
│     ↓                                 │                     │
│ [Parse PDF/Doc] ←────────────────────┘                     │
│     ↓                                                        │
│ [Normalize to Canonical]                                    │
│     ↓                                                        │
│ [Classify for PII] ← deterministic regex patterns           │
│     ↓                                                        │
│ [Redact if needed]                                          │
│     ↓                                                        │
│ [Emit to SDK] ← send structured payload                     │
│     ↓                                                        │
│ [Checkpoint] ← store state for resumption                   │
│                                                              │
│ State: (source_id, object_id, raw_content, parsed_doc,      │
│         normalized_doc, dlp_verdict, errors, trace_id)     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ Payload:
                     │ {
                     │   document_id,
                     │   source_id,
                     │   text (redacted),
                     │   blocks (canonical),
                     │   dlp_verdict,
                     │   trace_id
                     │ }
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ YOUR SDK (existing, external)                               │
│ Chunk → Embed → Store in Memory → Return memory_id          │
└─────────────────────────────────────────────────────────────┘
```

---

## Why LangGraph? Why No Skills Here?

| Question | Answer |
|----------|--------|
| **Why LangGraph?** | Clear state flow, checkpointable for resumption, built-in logging, integrates with agents for Phase 2 |
| **Why no skills?** | Skills are governance gates. Ingestion is execution. No judgment needed — process everything deterministically, classify for governance later. |
| **Then why keep skills?** | Documentation + foundation for Phase 2. Once a document is ingested, skills will gate approval (human review before a fact reaches the knowledge graph). |
| **Deterministic tools enough?** | For MVP, yes. PII detection is regex-based + heuristics. You can upgrade to ML later; architecture doesn't change. |

---

## What Changes (The Three Categories)

### CREATE (6 new files)

| File | Purpose | Lines |
|------|---------|-------|
| `agents/ingestion_workflow.py` | LangGraph state machine, 9 nodes | 350 |
| `common/tools/__init__.py` | Tool package exports | 10 |
| `common/tools/dlp_classifier.py` | PII patterns, redaction | 150 |
| `common/tools/source_connector.py` | Fetch blob/database content | 120 |
| `common/tools/document_normalizer.py` | Parser output → canonical | 80 |
| `common/tools/checkpoint_manager.py` | Persist/resume state | 100 |

### MODIFY (3 existing files)

| File | Change | Impact |
|------|--------|--------|
| `agents/connector_agent/agent.py` | After observe, call ingestion workflow | Wires Connectors → Ingestion |
| `agents/connector_agent/contracts.py` | Add `ingestion_results` field to response | Passes results back to caller |
| `.env` | Add 4 new configuration variables | Enables SDK endpoint, DLP threshold, checkpoint path |

### NO CHANGE (keep as-is)

| Package | Reason |
|---------|--------|
| `skills/Connect_Ingest_Ground/` | Stay as docs + Phase 2 governance gates |
| `ingestion/parsers/` | Already working, canonical output shape correct |
| `ingestion/models.py` | CanonicalDocument is the right contract |
| Connectors Agent | Registry + credential + connect stage unchanged |

---

## The 9 Nodes of the Workflow (Linear Path)

Each node is **deterministic** — same input always produces same output. No ML, no judgment, no retries.

| Node | Input | Job | Output | Fails? |
|------|-------|-----|--------|--------|
| **route** | state.kind | Decide which path: structured or unstructured | state._next_node | Never |
| **fetch_unstructured** | connection_handle, object_id | Download file from Azure Blob (or Google Docs) | state.raw_content (bytes) | Add to errors, continue |
| **fetch_structured** | connection_handle, schema | Query Snowflake for schema + 1 sample row | state.raw_content (dict) | Add to errors, continue |
| **parse** | state.raw_content | Detect MIME, dispatch to parser (PDF/CSV/Excel/Text/Docling) | state.parsed_doc (CanonicalDocument) | Add to errors, continue |
| **normalize** | state.parsed_doc | Convert to canonical shape (already done by parsers, just pass through) | state.normalized_doc | Add to errors, continue |
| **classify_dlp** | state.normalized_doc blocks | Regex + heuristics: identify PII patterns, sensitivity level | state.dlp_verdict | Add to warnings (never blocks) |
| **redact** | state.normalized_doc + dlp_verdict | Replace [SSN/CC/API_KEY] with [REDACTED] | state.redacted_text | Add to warnings (never blocks) |
| **emit** | state.redacted_text + metadata | POST to SDK endpoint: `/ingest` | state.ready_for_sdk = True | Add to errors (log failure) |
| **checkpoint** | full state | Save checkpoint for resumption | state.checkpoint_id | Add to warnings (log failure) |

**Failure mode:** Add to errors list and continue to next node. No retry, no backoff, no fallback.

---

## Tools Responsibility Matrix

### `dlp_classifier.py`

```
Input:  text (any length), optional column_name
Output: {sensitivity, patterns_found, confidence}

Patterns (regex):
  - SSN: \d{3}-\d{2}-\d{4}
  - EMAIL: [\w\.-]+@...
  - PHONE, CREDIT_CARD, API_KEY
  
Column heuristics:
  - If column name contains *_pii or sensitive_* → boost to PII

Result:
  - PUBLIC: no patterns, low column risk
  - INTERNAL: some patterns OR high column risk
  - PII: SSN/CC found OR very high confidence
```

### `source_connector.py`

```
For unstructured (fetch_unstructured):
  Input:  adapter ("azure-blob"), object_id
  Output: raw_bytes
  Job:    Download from blob/drive/etc using proven connection
  
For structured (fetch_structured):
  Input:  adapter ("snowflake"), schema name
  Output: dict with schema + sample row
  Job:    Query INFORMATION_SCHEMA + 1 data row
```

### `document_normalizer.py`

```
Input:  parsed_doc (varies by parser), adapter
Output: CanonicalDocument (standard shape)
Job:    For unstructured: already normalized by parser, pass through
        For structured: convert schema rows to block elements
```

### `checkpoint_manager.py`

```
save(source_id, object_id, state) → checkpoint_id
load(source_id, object_id) → state (or None)
mark_complete(source_id, object_id, revision)

File-based store: .ingestion_checkpoints/
  Later: swap for DB/Redis, same interface
```

---

## Trace ID & Observability

Every ingestion run carries a `trace_id` (UUID) that propagates through:
- Connectors Agent → IngestionState
- Every node appends to logs with trace_id
- Emitted to SDK in payload
- Stored in checkpoint

**Example log line:**
```
{
  "timestamp": "2026-09-03T12:00:00Z",
  "trace_id": "tr_abc123def456",
  "node": "parse_document",
  "status": "success",
  "object_id": "contract_2024_q3.pdf",
  "duration_ms": 245
}
```

**Later tracing:** Any failure or question traces back to this ID. No guessing about which run failed.

---

## SDK Hand-off Payload Format

```json
{
  "document_id": "contract_2024_q3.pdf",
  "source_id": "azure-blob-contracts",
  "revision": "etag_abc123",
  "adapter": "azure-blob",
  "kind": "unstructured",
  
  "metadata": {
    "mime_type": "application/pdf",
    "file_size_bytes": 125000,
    "ingestion_time": "2026-09-03T12:00:00Z"
  },
  
  "text": "Customer ABC agrees to deliver...",
  
  "blocks": [
    {
      "id": "blk_1",
      "type": "paragraph",
      "text": "First paragraph...",
      "page": 1,
      "source_start": 0
    },
    {
      "id": "blk_2",
      "type": "table",
      "text": "Rate | Discount\n50% | 5%",
      "page": 2
    }
  ],
  
  "dlp_verdict": {
    "sensitivity": "INTERNAL",
    "patterns_found": ["API_KEY"],
    "block_verdicts": [
      {"block_id": "blk_3", "sensitivity": "INTERNAL"}
    ]
  },
  
  "trace_id": "tr_abc123def456"
}
```

**Your SDK responds:**
```json
{
  "memory_id": "mem_xyz789",
  "chunks_count": 24,
  "embeddings_count": 24,
  "tokens_used": 3500
}
```

---

## Implementation Sequence (Do This Order)

### Week 1 — Core Pipeline
1. Create `common/tools/` package with 5 modules (150 lines total)
   - Test each tool independently
2. Create `agents/ingestion_workflow.py` with LangGraph graph (350 lines)
   - Test each node in isolation
3. Write integration tests for full workflow
4. Modify Connectors Agent to call ingestion after observation

### Week 2 — Integration
5. Wire your SDK endpoint into `emit_to_sdk` node
6. Test end-to-end: Connectors → Ingestion → SDK
7. Validate checkpoint store, resumption
8. Deploy, monitor traces

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Node failure leaves state orphaned | Checkpoint at every node; resumption logic |
| DLP patterns miss real PII | Regex only, add ML later; use conservative heuristics |
| SDK endpoint unavailable | Log error, don't block; checkpoint marked "emit_failed" |
| SDK payload wrong shape | Test with mock SDK locally first |
| Trace_id lost midway | Carried through entire state, logged everywhere |

---

## Validation Checklist Before Going Live

- [ ] All 5 tools created, unit-tested
- [ ] Workflow graph built, each node tested in isolation
- [ ] Full workflow integration tested with mock SDK
- [ ] Checkpoint save/load works, resumption tested
- [ ] DLP classifier tested on real samples (true/false positives)
- [ ] Trace IDs visible in logs, parseable by grep
- [ ] .env variables documented in README
- [ ] Error handling: no silent failures, all logged
- [ ] Connectors → Ingestion integration tested
- [ ] Ingestion → SDK integration tested with real endpoint

---

## Success Criteria

By end of 2 weeks you should have:

✅ **Deterministic pipeline**
- Input file → deterministic output every time
- Same trace_id allows full replay

✅ **No dependencies on Phase 2 (governance)**
- Ingestion works standalone
- Skills sit on shelf, unused

✅ **Measurable observation**
- Every step logged with trace_id
- Can grep logs for trace_id and see full flow

✅ **Ready for Phase 2**
- Output payload structure ready for knowledge graph ingestion
- DLP verdict captured (can be gated by human approval later)

---

## Questions Before You Start?

If you're unclear on:
- LangGraph syntax → see full design doc, has complete code
- Tool responsibilities → see matrix above and checklist
- Payload format → see JSON examples and emit_to_sdk node code
- Checkpoint logic → see checkpoint_manager.py code

Refer to the two detailed documents:
1. **ingestion_pipeline_design.md** — full code, every function
2. **ingestion_implementation_checklist.md** — file by file, what to type

Good luck. This is a clean, deterministic, testable architecture. Build it piece by piece and it'll work.
