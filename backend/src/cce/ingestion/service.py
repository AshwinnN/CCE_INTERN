#!/usr/bin/env python3
"""Thin composition of ConnectorAgent -> ingestion_workflow.run_ingestion(),
one call per change event. This is where "Connectors -> Ingestion" actually
gets wired (ingestion_pipeline_design.md's "High-Level Flow" diagram) --
deliberately NOT inside agents/connector_agent/agent.py, which stays
unaware this module exists (see agents/ingestion_workflow.py's module
docstring for why: agents/connector_agent/README.md's documented boundary,
"never reads or processes the content of what changed").

This module owns none of the Connector Agent's fail-closed logic and
reimplements none of it -- it calls ConnectorAgent.handle() exactly once and
fans its response's change_events out to run_ingestion(), one event at a
time. If the Connector Agent call itself is blocked/failed, there are no
events to ingest and this module reports that as zero ingestion_results,
not an ingestion error.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from cce.connectors.agent import ConnectorAgent
from cce.connectors.contracts import ConnectorRequest, ConnectorResponse
from cce.ingestion.orchestrator import run_ingestion
from cce.ingestion.checkpoint import IngestionCheckpointStore
from cce.persistence.ports import MetadataRepository


@dataclass
class IngestionOutcome:
    object_id: str
    change_type: str
    success: bool
    ingestion_checkpoint_id: Optional[str]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id,
            "change_type": self.change_type,
            "success": self.success,
            "ingestion_checkpoint_id": self.ingestion_checkpoint_id,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class PipelineResult:
    connector_response: ConnectorResponse
    ingestion_results: List[IngestionOutcome] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connector_response": self.connector_response.to_dict(),
            "ingestion_results": [r.to_dict() for r in self.ingestion_results],
        }


def run_pipeline(request: ConnectorRequest, *,
                  connector_agent: Optional[ConnectorAgent] = None,
                  schema_scope: Optional[List[str]] = None,
                  schema_database: Optional[str] = None,
                  fetch_unstructured_fn: Optional[Callable[[str, dict, str], bytes]] = None,
                  fetch_structured_fn: Optional[Callable[[str, dict, List[str]], dict]] = None,
                  sdk_emit_fn: Optional[Callable[[dict], dict]] = None,
                  checkpoint_store: Optional[IngestionCheckpointStore] = None,
                  metadata_repository: Optional[MetadataRepository] = None) -> PipelineResult:
    """Connect + observe via ConnectorAgent, then run every resulting
    change event through the ingestion workflow.

    `connector_agent` lets a caller reuse one ConnectorAgent (and therefore
    its checkpoint/dedup stores) across repeated poll cycles, the same way
    tests/connector_agent/test_connector_agent.py's ObservationTests do.
    `schema_database`/`metadata_repository` are passed straight through to
    run_ingestion() -- see its docstring.
    """
    agent = connector_agent or ConnectorAgent()
    response = agent.handle(request)

    connection_handle = {"handle_id": response.connection.get("connection_handle")}
    source_id = request.source_scope.get("source_id", request.source_adapter)

    outcomes: List[IngestionOutcome] = []
    for event in response.change_events:
        success, state = run_ingestion(
            event, connection_handle, source_id,
            trace_id=response.trace_id,
            schema_scope=schema_scope,
            schema_database=schema_database,
            fetch_unstructured_fn=fetch_unstructured_fn,
            fetch_structured_fn=fetch_structured_fn,
            sdk_emit_fn=sdk_emit_fn,
            checkpoint_store=checkpoint_store,
            metadata_repository=metadata_repository,
        )
        outcomes.append(IngestionOutcome(
            object_id=event["object"]["object_id"],
            change_type=event["change_type"],
            success=success,
            ingestion_checkpoint_id=state.get("ingestion_checkpoint_id"),
            errors=state.get("errors", []),
            warnings=state.get("warnings", []),
        ))

    return PipelineResult(connector_response=response, ingestion_results=outcomes)
