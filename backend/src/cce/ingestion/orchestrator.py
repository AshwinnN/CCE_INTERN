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
import hashlib
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, END

from cce.ingestion.checkpoint import IngestionCheckpointStore, get_ingestion_checkpoint_store
from cce.security.dlp import classify_text, get_dlp_confidence_threshold, redact_text
from cce.ingestion.normalizers.document import normalize_to_canonical
from cce.connectors.fetch import fetch_structured as _fetch_structured_card
from cce.connectors.fetch import fetch_unstructured as _fetch_unstructured_bytes
from cce.connectors.base.canonical_types import canonicalize_type
from cce.persistence.ports import MetadataRepository, SchemaSnapshot

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
    schema_database: Optional[str]  # structured lane only -- adapter's database/catalog name
                                     # (not present in SourceChangeEvent; see
                                     # persist_structured_metadata_node's _resolve_schema_database())
    trace_id: str

    # injected dependencies (test/caller-supplied; production defaults are
    # module-level functions below). Underscore-prefixed per this repo's
    # convention for fields that stand in for a live driver/service
    # (see change_capture.py's _objects/_catalog).
    _fetch_unstructured: Optional[Callable[[str, dict, str], bytes]]
    _fetch_structured: Optional[Callable[[str, dict, List[str]], dict]]
    _sdk_emit: Optional[Callable[[dict], dict]]
    _checkpoint_store: Optional[IngestionCheckpointStore]
    _metadata_repository: Optional[MetadataRepository]

    # --- intermediate ---
    raw_content: Optional[Any]         # bytes (unstructured) | dict schema card (structured)
    parsed_doc: Optional[dict]         # CanonicalDocument-shaped, unstructured only
    normalized_doc: Optional[dict]     # CanonicalDocument-shaped, both lanes
    metadata_snapshot_id: Optional[str]  # structured lane only -- set by persist_structured_metadata_node

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
    object_id = state["event"]["object"]["object_id"]
    try:
        logger.info("fetch_unstructured: object_id=%s adapter=%s trace_id=%s",
                    object_id, state["adapter"], state.get("trace_id"))
        state["raw_content"] = _fetch_unstructured_bytes(
            state["adapter"], state["connection_handle"], object_id,
            state.get("_fetch_unstructured"),
        )
        logger.info("fetch_unstructured: object_id=%s fetched %d bytes",
                    object_id, len(state["raw_content"] or b""))
    except Exception as e:
        logger.error("fetch_unstructured failed: object_id=%s error=%s", object_id, e)
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
    from cce.connectors.fetch import snowflake_schema_fetcher
    return snowflake_schema_fetcher()(adapter, connection_handle, schema_scope)


def fetch_structured_node(state: IngestionState) -> IngestionState:
    """Fetch a schema card (schema + sample rows) for the structured lane."""
    schema_scope = state.get("schema_scope", [])
    try:
        logger.info("fetch_structured: adapter=%s schema_scope=%s trace_id=%s",
                    state["adapter"], schema_scope, state.get("trace_id"))
        state["raw_content"] = _fetch_structured_card(
            state["adapter"], state["connection_handle"], schema_scope,
            state.get("_fetch_structured") or _default_fetch_structured,
        )
        tables = (state["raw_content"] or {}).get("tables", [])
        logger.info("fetch_structured: schema=%s fetched %d tables",
                    (state["raw_content"] or {}).get("schema"), len(tables))
    except Exception as e:
        logger.error("fetch_structured failed: adapter=%s schema_scope=%s error=%s",
                     state["adapter"], schema_scope, e)
        state["errors"] = state["errors"] + ["fetch_structured: %s" % e]
    return state


def _default_metadata_repository() -> Optional[MetadataRepository]:
    """Production default: PostgreSQLMetadataRepository from
    CCE_CONTROL_DATABASE_URL. None (dry run) if unset -- matches
    _default_sdk_emit's "endpoint not configured -> dry run" pattern above:
    a metadata-repository outage or absence must never block the SDK emit,
    which stays this pipeline's critical path (see
    persist_structured_metadata_node's docstring)."""
    dsn = os.environ.get("CCE_CONTROL_DATABASE_URL") or os.environ.get("CCE_METADATA_DATABASE_URL")
    if not dsn:
        return None
    from cce.persistence.postgres.metadata_repository import PostgreSQLMetadataRepository
    return PostgreSQLMetadataRepository(dsn)


def _resolve_schema_database(adapter: str, explicit: Optional[str]) -> Optional[str]:
    """The adapter's database/catalog name -- not present anywhere in
    SourceChangeEvent (see agents/connector_agent/contracts.py), so an
    explicit override (run_ingestion(schema_database=...)) always wins.
    Falls back to env for adapter == "snowflake" only, the same
    single-adapter special case _default_fetch_structured makes above.
    An incomplete CCE_SNOWFLAKE_* env (e.g. a test/dev environment with a
    repository configured but no live Snowflake account) degrades to None
    (caller substitutes "default") rather than aborting the whole persist
    attempt -- getting the namespace name wrong is recoverable, losing the
    entire snapshot over it is not."""
    if explicit:
        return explicit
    if adapter == "snowflake":
        try:
            from cce.connectors.structured.snowflake.config import build_config_from_env
            return build_config_from_env().database
        except KeyError:
            return None
    return None


def persist_structured_metadata_node(state: IngestionState) -> IngestionState:
    """Structured lane only: canonicalize every column's native type
    (connectors/canonical_types.py -- "Issue 5: Canonical Types") and
    persist a new immutable snapshot (source -> namespace -> schema ->
    table -> column) to the metadata repository (schema/*.sql). No-op
    passthrough for the unstructured lane, same pattern as
    parse_document_node's `if state["kind"] != "structured"` check.

    A repository failure -- including "no CCE_CONTROL_DATABASE_URL
    configured" -- becomes a warning, never an error: this step is
    additive to the pipeline's critical path (fetch -> normalize -> emit
    to CCE_SDK_ENDPOINT), matching this file's existing
    classify/redact/checkpoint "never blocks" discipline.
    """
    if state["kind"] != "structured":
        return state
    schema_card = state.get("raw_content")
    if not schema_card:
        return state  # fetch_structured already recorded why

    repo = state.get("_metadata_repository")
    owns_repo = repo is None
    try:
        if repo is None:
            repo = _default_metadata_repository()
        if repo is None:
            state["warnings"] = state["warnings"] + [
                "persist_structured_metadata: CCE_CONTROL_DATABASE_URL not configured, dry-run only"]
            return state

        adapter = state["adapter"]
        database_name = _resolve_schema_database(adapter, state.get("schema_database")) or "default"
        source_id = repo.ensure_source(adapter, state["source_id"])
        namespace_type = "catalog" if adapter == "snowflake" else "database"
        namespace_id = repo.ensure_namespace(source_id, database_name, namespace_type)
        schema_name = schema_card.get("schema") or "default"
        schema_id = repo.ensure_schema(namespace_id, schema_name)

        tables = schema_card.get("tables", [])
        schema_hash = hashlib.sha256(
            json.dumps(tables, sort_keys=True, default=str).encode()).hexdigest()
        snapshot_id = str(uuid.uuid4())
        repo.save_snapshot(SchemaSnapshot(
            snapshot_id=snapshot_id, source_id=source_id, schema_id=schema_id,
            captured_at=datetime.now(timezone.utc), schema_hash=schema_hash, status="SUCCESS",
            table_count=len(tables), column_count=sum(len(t.get("columns", [])) for t in tables),
        ))

        for table in tables:
            table_id = repo.save_table({
                "snapshot_id": snapshot_id, "schema_id": schema_id,
                "table_name": table.get("name"), "table_type": "TABLE",
                "row_count": table.get("row_count"),
            })
            for ordinal, col in enumerate(table.get("columns", []), start=1):
                data_type, type_detail = canonicalize_type(col.get("type") or "", adapter)
                repo.save_column({
                    "snapshot_id": snapshot_id, "table_id": table_id,
                    "column_name": col.get("name"), "ordinal_position": ordinal,
                    "data_type": data_type, "type_detail": type_detail,
                    "native_data_type": col.get("type"),
                    "is_nullable": col.get("nullable", True),
                    "numeric_precision": type_detail.get("precision"),
                    "numeric_scale": type_detail.get("scale"),
                    "character_maximum_length": type_detail.get("length"),
                })

        state["metadata_snapshot_id"] = snapshot_id
        logger.info(
            "persist_structured_metadata: snapshot_id=%s schema=%s tables=%d columns=%d",
            snapshot_id, schema_name, len(tables),
            sum(len(t.get("columns", [])) for t in tables),
        )
    except Exception as e:
        logger.warning("persist_structured_metadata failed (non-fatal): %s", e)
        state["warnings"] = state["warnings"] + ["persist_structured_metadata: %s" % e]
    finally:
        if owns_repo and repo is not None:
            repo.close()
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
        from cce.ingestion.change_detection.file_detection import detect_mime_type
        from cce.ingestion.models import DocumentMetadata
        from cce.ingestion.parsers.factory import ParserFactory

        object_id = state["event"]["object"]["object_id"]
        suffix = os.path.splitext(object_id)[1] or ".tmp"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name

        mime_type = detect_mime_type(tmp_path)
        logger.info("parse_document: object_id=%s mime_type=%s size=%d bytes",
                    object_id, mime_type, len(raw))
        parser = ParserFactory.get_parser(mime_type)
        if parser is None:
            logger.error("parse_document: object_id=%s unsupported mime_type=%s", object_id, mime_type)
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
            elements = state["parsed_doc"].get("elements", [])
            logger.info("parse_document: object_id=%s status=%s -> %d elements",
                        object_id, result.status.value, len(elements))
            if result.warnings:
                state["warnings"] = state["warnings"] + list(result.warnings)
        else:
            logger.error("parse_document: object_id=%s parser reported status=%s",
                         object_id, result.status.value)
            state["errors"] = state["errors"] + (
                list(result.errors) if result.errors
                else ["parse_document: parser reported %s" % result.status.value])
    except Exception as e:
        logger.error("parse_document failed: object_id=%s error=%s", object_id, e)
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
        state["normalized_doc"] = normalize_to_canonical(
            source_payload, state["kind"], source_database=state["adapter"])
        elements = (state["normalized_doc"] or {}).get("elements", [])
        logger.info("normalize_document: kind=%s -> %d canonical elements",
                    state["kind"], len(elements))
    except Exception as e:
        logger.error("normalize_document failed: kind=%s error=%s", state["kind"], e)
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
            "source_ref": event["object"].get("source_ref") or event["object"]["object_id"],
            "object_id": event["object"]["object_id"],
            "adapter": state["adapter"],
            "kind": state["kind"],
            "change_type": event.get("change_type"),
            "tenant_id": state.get("tenant_id"),
            "metadata": doc.get("metadata", {}),
            "blocks": doc.get("elements", []),
            "dlp_verdict": state.get("dlp_verdict"),
            "trace_id": state["trace_id"],
        }
        logger.info(
            "emit_to_sdk: document_id=%s source_id=%s change_type=%s blocks=%d "
            "sensitivity=%s trace_id=%s",
            payload["document_id"], payload["source_id"], payload["change_type"],
            len(payload["blocks"]), (payload.get("dlp_verdict") or {}).get("sensitivity"),
            payload["trace_id"],
        )
        emit_fn = state.get("_sdk_emit") or _default_sdk_emit
        state["sdk_response"] = emit_fn(payload)
        state["ready_for_sdk"] = True
        logger.info("emit_to_sdk: document_id=%s response=%s",
                    payload["document_id"], state["sdk_response"])
    except Exception as e:
        logger.error("emit_to_sdk failed: document_id=%s error=%s",
                     event.get("object", {}).get("object_id"), e)
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
            "metadata_snapshot_id": state.get("metadata_snapshot_id"),
            "trace_id": state["trace_id"],
        }
        state["ingestion_checkpoint_id"] = store.save(state["source_id"], object_id, checkpoint_data)
        logger.info("checkpoint: object_id=%s status=%s checkpoint_id=%s",
                    object_id, checkpoint_data["status"], state["ingestion_checkpoint_id"])
    except Exception as e:
        logger.warning("checkpoint failed (non-fatal): %s", e)
        state["warnings"] = state["warnings"] + ["checkpoint: %s" % e]
    return state


# ===== BUILD THE GRAPH =====

def build_ingestion_workflow():
    workflow = StateGraph(IngestionState)

    workflow.add_node("route", route_by_source)
    workflow.add_node("fetch_unstructured", fetch_unstructured_node)
    workflow.add_node("fetch_structured", fetch_structured_node)
    workflow.add_node("persist_structured_metadata", persist_structured_metadata_node)
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
    workflow.add_edge("fetch_structured", "persist_structured_metadata")
    workflow.add_edge("persist_structured_metadata", "normalize")
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
                   schema_database: Optional[str] = None,
                   fetch_unstructured_fn: Optional[Callable[[str, dict, str], bytes]] = None,
                   fetch_structured_fn: Optional[Callable[[str, dict, List[str]], dict]] = None,
                   sdk_emit_fn: Optional[Callable[[dict], dict]] = None,
                   checkpoint_store: Optional[IngestionCheckpointStore] = None,
                   metadata_repository: Optional[MetadataRepository] = None):
    """Entry point: given one SourceChangeEvent-shaped dict (as produced by
    agents/connector_agent/change_capture.py's observers), run it through
    the full ingestion workflow.

    kind/adapter are read from event["source"] rather than taken as separate
    arguments -- the event is the single source of truth for what it is, and
    the Connector Agent always sets both fields (see change_capture.py's
    _event() helpers).

    schema_database (structured lane only) is the adapter's database/catalog
    name for persist_structured_metadata_node -- see
    _resolve_schema_database()'s docstring for why it can't be read off the
    event. metadata_repository lets a caller reuse one repository (and its
    connection pool) across repeated ingestion runs, the same way
    checkpoint_store is reused; a caller-supplied repository is never closed
    by this workflow (see persist_structured_metadata_node's `owns_repo`).

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
        "schema_database": schema_database,
        "trace_id": trace_id or event.get("trace_id") or "",
        "_fetch_unstructured": fetch_unstructured_fn,
        "_fetch_structured": fetch_structured_fn,
        "_sdk_emit": sdk_emit_fn,
        "_checkpoint_store": checkpoint_store,
        "_metadata_repository": metadata_repository,
        "raw_content": None,
        "parsed_doc": None,
        "normalized_doc": None,
        "metadata_snapshot_id": None,
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
