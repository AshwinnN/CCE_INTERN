#!/usr/bin/env python3
"""Ingest & Ground's execution stage: a deterministic LangGraph state machine
that takes one SourceChangeEvent-shaped dict from the Connector Agent
(agents/connector_agent/contracts.py's SourceChangeEvent, or the equivalent
dict agents/connector_agent/change_capture.py's observers build) and carries
it through fetch -> parse -> normalize -> classify -> redact -> emit ->
checkpoint. See ingestion_pipeline_design.md and ingestion_summary.md for the
architecture rationale.

Every node is deterministic -- no ML, no judgment, no retries. A node that
fails appends to state["errors"] (fetch/parse/normalize/emit) or
state["warnings"] (classify/redact/checkpoint -- "never blocks" per the
design's node responsibility matrix) and the graph continues to the next
node regardless; run_ingestion()'s success return is simply "errors is
empty" at the end.

This module calls NO skill and imports nothing from skills/ -- ingestion is
execution, not governance, matching agents/connector_agent/agent.py's own
FORBIDDEN_SKILLS discipline for the same reason (skills stay Phase 2
governance gates; see ingestion_summary.md, "Why no skills here?").

Wiring: this module is intentionally NOT called from
agents/connector_agent/agent.py -- that Agent's documented contract is
"never reads or processes the content of what changed"
(agents/connector_agent/README.md). agents/ingestion_pipeline.py is the
thin, separate orchestrator that chains ConnectorAgent.handle() into
run_ingestion() per event, so this boundary stays intact.
"""
import copy
import logging
import os
import tempfile
from typing import Any, Callable, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, END

from common.tools.checkpoint_manager import IngestionCheckpointStore, get_ingestion_checkpoint_store
from common.tools.dlp_classifier import classify_text, get_dlp_confidence_threshold, redact_text
from common.tools.document_normalizer import normalize_to_canonical
from common.tools.source_connector import fetch_structured as _fetch_structured_card
from common.tools.source_connector import fetch_unstructured as _fetch_unstructured_bytes

logger = logging.getLogger(__name__)


# ===== STATE SHAPE =====

class IngestionState(TypedDict, total=False):
    # --- input, set once by run_ingestion() ---
    source_id: str
    tenant_id: Optional[str]
    kind: str                      # "structured" | "unstructured" -- from event["source"]["kind"]
    adapter: str                   # from event["source"]["adapter"]
    connection_handle: dict
    event: dict                    # full SourceChangeEvent-shaped dict
    schema_scope: List[str]
    trace_id: str

    # injected dependencies (test/caller-supplied; production defaults are
    # module-level functions below). Underscore-prefixed per this repo's
    # convention for fields that stand in for a live driver/service
    # (see change_capture.py's _objects/_catalog).
    _fetch_unstructured: Optional[Callable[[str, dict, str], bytes]]
    _fetch_structured: Optional[Callable[[str, dict, List[str]], dict]]
    _sdk_emit: Optional[Callable[[dict], dict]]
    _checkpoint_store: Optional[IngestionCheckpointStore]

    # --- intermediate ---
    raw_content: Optional[Any]         # bytes (unstructured) | dict schema card (structured)
    parsed_doc: Optional[dict]         # CanonicalDocument-shaped, unstructured only
    normalized_doc: Optional[dict]     # CanonicalDocument-shaped, both lanes

    dlp_verdict: Optional[dict]
    redacted_doc: Optional[dict]

    errors: List[str]
    warnings: List[str]

    ready_for_sdk: bool
    sdk_response: Optional[dict]

    ingestion_checkpoint_id: Optional[str]

    _next_node: str


# ===== WORKFLOW NODES =====

def route_by_source(state: IngestionState) -> IngestionState:
    """Deterministic router: a deleted object has nothing to fetch/parse --
    it goes straight to emit (a tombstone payload) so the SDK can remove it
    from memory. Otherwise fork on kind, never on adapter (see module
    docstring and agents/connector_agent/router.py's same discipline)."""
    if state["event"].get("change_type") == "deleted":
        state["_next_node"] = "emit"
    elif state["kind"] == "structured":
        state["_next_node"] = "fetch_structured"
    else:
        state["_next_node"] = "fetch_unstructured"
    return state


def fetch_unstructured_node(state: IngestionState) -> IngestionState:
    """Download raw bytes from the unstructured source using the connection
    handle the Connector Agent already proved read-only."""
    try:
        object_id = state["event"]["object"]["object_id"]
        state["raw_content"] = _fetch_unstructured_bytes(
            state["adapter"], state["connection_handle"], object_id,
            state.get("_fetch_unstructured"),
        )
    except Exception as e:
        state["errors"] = state["errors"] + ["fetch_unstructured: %s" % e]
    return state


def _default_fetch_structured(adapter: str, connection_handle: dict, schema_scope: List[str]) -> dict:
    """Production default: a real, live connectors/ connector, not a
    simulated one. Only "snowflake" has a real implementation today (see
    connectors/snowflake/) -- an adapter with none raises a clear error
    rather than a silent no-op, same discipline as every other "no default
    for this adapter yet" gap in this repo."""
    if adapter != "snowflake":
        raise RuntimeError(
            "fetch_structured: no default fetcher for adapter %r (only 'snowflake' has one; "
            "inject fetch_structured_fn for others)" % adapter)
    from common.tools.source_connector import snowflake_schema_fetcher
    return snowflake_schema_fetcher()(adapter, connection_handle, schema_scope)


def fetch_structured_node(state: IngestionState) -> IngestionState:
    """Fetch a schema card (schema + sample rows) for the structured lane."""
    try:
        state["raw_content"] = _fetch_structured_card(
            state["adapter"], state["connection_handle"], state.get("schema_scope", []),
            state.get("_fetch_structured") or _default_fetch_structured,
        )
    except Exception as e:
        state["errors"] = state["errors"] + ["fetch_structured: %s" % e]
    return state


def parse_document_node(state: IngestionState) -> IngestionState:
    """Unstructured only: detect MIME, dispatch to a parser, parse raw bytes
    into a CanonicalDocument. No-op (state unchanged) for the structured
    lane -- fetch_structured already returns a normalize-ready schema card,
    matching the design's fetch_structured -> normalize edge that skips
    parse entirely."""
    if state["kind"] != "unstructured":
        return state
    raw = state.get("raw_content")
    if not raw:
        return state  # fetch_unstructured already recorded why

    tmp_path = None
    try:
        from ingestion.file_detection import detect_mime_type
        from ingestion.models import DocumentMetadata
        from ingestion.parsers.factory import ParserFactory

        object_id = state["event"]["object"]["object_id"]
        suffix = os.path.splitext(object_id)[1] or ".tmp"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name

        mime_type = detect_mime_type(tmp_path)
        parser = ParserFactory.get_parser(mime_type)
        if parser is None:
            state["errors"] = state["errors"] + [
                "parse_document: unsupported mime type %s" % mime_type]
            return state

        doc_metadata = DocumentMetadata(
            document_id=object_id,
            source_system=state["adapter"],
            source_uri=state["event"]["object"].get("source_ref") or object_id,
            mime_type=mime_type,
        )
        result = parser.parse(tmp_path, doc_metadata)
        if result.status.value in ("SUCCESS", "PARTIAL"):
            state["parsed_doc"] = result.document.model_dump(mode="json")
            if result.warnings:
                state["warnings"] = state["warnings"] + list(result.warnings)
        else:
            state["errors"] = state["errors"] + (
                list(result.errors) if result.errors
                else ["parse_document: parser reported %s" % result.status.value])
    except Exception as e:
        state["errors"] = state["errors"] + ["parse_document: %s" % e]
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return state


def normalize_document_node(state: IngestionState) -> IngestionState:
    """Convert the lane-specific payload to the shared CanonicalDocument
    shape. Unstructured: parsed_doc is already that shape, passed through.
    Structured: raw_content (the schema card) is converted to blocks."""
    try:
        source_payload = state.get("parsed_doc") if state["kind"] == "unstructured" \
            else state.get("raw_content")
        state["normalized_doc"] = normalize_to_canonical(source_payload, state["kind"])
    except Exception as e:
        state["errors"] = state["errors"] + ["normalize_document: %s" % e]
    return state


def _iter_text_blocks(elements: List[dict]):
    """Yield (block_id, text) for every classifiable span in a
    CanonicalDocument's elements -- top-level text (TEXT/HEADING/PARAGRAPH/
    LIST_ITEM elements) and, for TABLE elements, each cell's text."""
    for el in elements or []:
        text = el.get("text")
        if text:
            yield el.get("id"), text
        for cell in el.get("cells") or []:
            if not isinstance(cell, dict):
                continue
            cell_text = cell.get("text")
            if cell_text:
                yield "%s:cell:%s:%s" % (el.get("id"), cell.get("row"), cell.get("col")), cell_text


def classify_for_dlp_node(state: IngestionState) -> IngestionState:
    """Deterministic PII/sensitivity classification for every text block.
    Never blocks the pipeline -- a classification failure is a warning,
    not an error (see ingestion_summary.md's node responsibility matrix)."""
    doc = state.get("normalized_doc")
    if not doc:
        return state
    try:
        block_verdicts = [
            {"block_id": block_id, **classify_text(text)}
            for block_id, text in _iter_text_blocks(doc.get("elements", []))
        ]
        rank = {"PUBLIC": 0, "INTERNAL": 1, "PII": 2}
        max_sensitivity = "PUBLIC"
        for v in block_verdicts:
            if rank[v["sensitivity"]] > rank[max_sensitivity]:
                max_sensitivity = v["sensitivity"]
        state["dlp_verdict"] = {"sensitivity": max_sensitivity, "block_verdicts": block_verdicts}
    except Exception as e:
        state["warnings"] = state["warnings"] + ["classify_for_dlp: %s" % e]
        state["dlp_verdict"] = {"sensitivity": "INTERNAL", "block_verdicts": []}
    return state


def _should_redact(block_verdict: dict, threshold: float) -> bool:
    if block_verdict["sensitivity"] == "PII":
        return True
    if block_verdict["sensitivity"] == "INTERNAL" and block_verdict.get("confidence", 0) >= threshold:
        return True
    return False


def redact_if_needed_node(state: IngestionState) -> IngestionState:
    """Redact only the blocks classify_for_dlp flagged, at or above
    CCE_DLP_CONFIDENCE_THRESHOLD (PII always redacts regardless of
    confidence). Passes normalized_doc through unchanged if there's nothing
    to redact against."""
    doc = state.get("normalized_doc")
    verdict = state.get("dlp_verdict")
    if not doc or not verdict:
        state["redacted_doc"] = doc
        return state
    try:
        threshold = get_dlp_confidence_threshold()
        by_block = {v["block_id"]: v for v in verdict.get("block_verdicts", [])}
        redacted = copy.deepcopy(doc)
        for el in redacted.get("elements", []):
            v = by_block.get(el.get("id"))
            if v and _should_redact(v, threshold) and el.get("text"):
                el["text"] = redact_text(el["text"])
            for cell in el.get("cells") or []:
                if not isinstance(cell, dict):
                    continue
                cv = by_block.get("%s:cell:%s:%s" % (el.get("id"), cell.get("row"), cell.get("col")))
                if cv and _should_redact(cv, threshold) and cell.get("text"):
                    cell["text"] = redact_text(cell["text"])
        state["redacted_doc"] = redacted
    except Exception as e:
        state["warnings"] = state["warnings"] + ["redact_if_needed: %s" % e]
        state["redacted_doc"] = doc
    return state


def _default_sdk_emit(payload: dict) -> dict:
    """Production emit: POST to CCE_SDK_ENDPOINT. If it isn't configured,
    this is a dry run -- logged, not an error, since a caller may not yet
    have an SDK endpoint to hand off to (see .env.example)."""
    endpoint = os.environ.get("CCE_SDK_ENDPOINT")
    if not endpoint:
        logger.info("emit_to_sdk: CCE_SDK_ENDPOINT not configured, dry-run only (trace_id=%s)",
                     payload.get("trace_id"))
        return {"status": "dry_run", "reason": "CCE_SDK_ENDPOINT not configured"}

    import requests
    headers = {}
    api_key = os.environ.get("CCE_SDK_API_KEY")
    if api_key:
        headers["Authorization"] = "Bearer %s" % api_key
    response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def emit_to_sdk_node(state: IngestionState) -> IngestionState:
    """Package the classified, redacted document (or, for a deletion, a
    tombstone with no blocks) and hand it to the SDK's ingest endpoint."""
    try:
        event = state["event"]
        doc = state.get("redacted_doc") or state.get("normalized_doc") or {}
        payload = {
            "document_id": event["object"]["object_id"],
            "source_id": state["source_id"],
            "revision": event["object"].get("version"),
            "adapter": state["adapter"],
            "kind": state["kind"],
            "change_type": event.get("change_type"),
            "tenant_id": state.get("tenant_id"),
            "metadata": doc.get("metadata", {}),
            "blocks": doc.get("elements", []),
            "dlp_verdict": state.get("dlp_verdict"),
            "trace_id": state["trace_id"],
        }
        emit_fn = state.get("_sdk_emit") or _default_sdk_emit
        state["sdk_response"] = emit_fn(payload)
        state["ready_for_sdk"] = True
    except Exception as e:
        state["errors"] = state["errors"] + ["emit_to_sdk: %s" % e]
        state["ready_for_sdk"] = False
    return state


def checkpoint_node(state: IngestionState) -> IngestionState:
    """Persist the run's outcome for resumption -- keyed by
    (source_id, object_id), distinct from the Connector Agent's own
    per-source_id observation cursor (common/checkpoint_store.py)."""
    try:
        store = state.get("_checkpoint_store") or get_ingestion_checkpoint_store()
        object_id = state["event"]["object"]["object_id"]
        checkpoint_data = {
            "source_id": state["source_id"],
            "object_id": object_id,
            "revision": state["event"]["object"].get("version"),
            "change_type": state["event"].get("change_type"),
            "status": "success" if not state["errors"] else "partial",
            "errors": state["errors"],
            "warnings": state["warnings"],
            "ready_for_sdk": state.get("ready_for_sdk", False),
            "trace_id": state["trace_id"],
        }
        state["ingestion_checkpoint_id"] = store.save(state["source_id"], object_id, checkpoint_data)
    except Exception as e:
        state["warnings"] = state["warnings"] + ["checkpoint: %s" % e]
    return state


# ===== BUILD THE GRAPH =====

def build_ingestion_workflow():
    workflow = StateGraph(IngestionState)

    workflow.add_node("route", route_by_source)
    workflow.add_node("fetch_unstructured", fetch_unstructured_node)
    workflow.add_node("fetch_structured", fetch_structured_node)
    workflow.add_node("parse", parse_document_node)
    workflow.add_node("normalize", normalize_document_node)
    workflow.add_node("classify_dlp", classify_for_dlp_node)
    workflow.add_node("redact", redact_if_needed_node)
    workflow.add_node("emit", emit_to_sdk_node)
    workflow.add_node("checkpoint", checkpoint_node)

    workflow.set_entry_point("route")

    def route_conditional(state: IngestionState) -> str:
        return state.get("_next_node", "fetch_unstructured")

    workflow.add_conditional_edges("route", route_conditional, {
        "fetch_unstructured": "fetch_unstructured",
        "fetch_structured": "fetch_structured",
        "emit": "emit",
    })

    workflow.add_edge("fetch_unstructured", "parse")
    workflow.add_edge("parse", "normalize")
    workflow.add_edge("fetch_structured", "normalize")
    workflow.add_edge("normalize", "classify_dlp")
    workflow.add_edge("classify_dlp", "redact")
    workflow.add_edge("redact", "emit")
    workflow.add_edge("emit", "checkpoint")
    workflow.add_edge("checkpoint", END)

    return workflow.compile()


# ===== INVOCATION =====

def run_ingestion(event: Dict[str, Any], connection_handle: dict, source_id: str, *,
                   trace_id: Optional[str] = None,
                   schema_scope: Optional[List[str]] = None,
                   fetch_unstructured_fn: Optional[Callable[[str, dict, str], bytes]] = None,
                   fetch_structured_fn: Optional[Callable[[str, dict, List[str]], dict]] = None,
                   sdk_emit_fn: Optional[Callable[[dict], dict]] = None,
                   checkpoint_store: Optional[IngestionCheckpointStore] = None):
    """Entry point: given one SourceChangeEvent-shaped dict (as produced by
    agents/connector_agent/change_capture.py's observers), run it through
    the full ingestion workflow.

    kind/adapter are read from event["source"] rather than taken as separate
    arguments -- the event is the single source of truth for what it is, and
    the Connector Agent always sets both fields (see change_capture.py's
    _event() helpers).

    Returns: (success: bool, final_state: IngestionState) -- success is
    "no node recorded an error", not "nothing recorded a warning".
    """
    workflow = build_ingestion_workflow()

    initial_state: IngestionState = {
        "source_id": source_id,
        "tenant_id": event.get("tenant_id"),
        "kind": event["source"]["kind"],
        "adapter": event["source"]["adapter"],
        "connection_handle": connection_handle,
        "event": event,
        "schema_scope": schema_scope or [],
        "trace_id": trace_id or event.get("trace_id") or "",
        "_fetch_unstructured": fetch_unstructured_fn,
        "_fetch_structured": fetch_structured_fn,
        "_sdk_emit": sdk_emit_fn,
        "_checkpoint_store": checkpoint_store,
        "raw_content": None,
        "parsed_doc": None,
        "normalized_doc": None,
        "dlp_verdict": None,
        "redacted_doc": None,
        "errors": [],
        "warnings": [],
        "ready_for_sdk": False,
        "sdk_response": None,
        "ingestion_checkpoint_id": None,
    }

    final_state = workflow.invoke(initial_state)
    return (len(final_state.get("errors", [])) == 0, final_state)
