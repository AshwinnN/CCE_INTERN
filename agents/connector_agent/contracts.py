#!/usr/bin/env python3
"""Source-agnostic request/response/event contracts for the Connector Agent.

Field names follow the shapes in the design prompt where they matched real
skill contracts; where they didn't (see registry capability keys), the real
skill contract wins per "use the exact names found in the codebase."
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


@dataclass
class ObservationSpec:
    mode: Optional[str] = None  # "start" | "resume" | "poll" | "stop" | None (connect-only call)
    checkpoint: Optional[str] = None


@dataclass
class ConnectorRequest:
    tenant_id: str
    source_adapter: str
    credential_ref: str
    request_id: Optional[str] = None
    requested_capabilities: List[str] = field(default_factory=list)
    source_scope: Dict[str, Any] = field(default_factory=dict)
    observation: ObservationSpec = field(default_factory=ObservationSpec)

    @staticmethod
    def from_dict(d: dict) -> "ConnectorRequest":
        obs = d.get("observation") or {}
        return ConnectorRequest(
            tenant_id=d["tenant_id"],
            source_adapter=d["source_adapter"],
            credential_ref=d.get("credential_ref", ""),
            request_id=d.get("request_id"),
            requested_capabilities=list(d.get("requested_capabilities", [])),
            source_scope=dict(d.get("source_scope", {})),
            observation=ObservationSpec(mode=obs.get("mode"), checkpoint=obs.get("checkpoint")),
        )


@dataclass
class SkillTraceEntry:
    skill: str
    status: str
    trace_id: str

    def to_dict(self):
        return {"skill": self.skill, "status": self.status, "trace_id": self.trace_id}


@dataclass
class ConnectorResponse:
    trace_id: str
    request_id: Optional[str]
    status: str  # "connected" | "observing" | "validated" | "blocked" | "failed"
    source: Dict[str, Any]
    connection: Dict[str, Any]
    capabilities: List[str]
    skill_trace: List[SkillTraceEntry]
    checkpoint: Optional[str] = None
    error: Optional[Dict[str, Any]] = None
    # The SourceChangeEvent-shaped dicts this call detected and handed off
    # (post-dedup, pre-checkpoint-advance -- see agent.py's _observe()).
    # Populated only for observation.mode in {start, resume, poll}; empty
    # for a connect-only call. This is data the Agent already computes for
    # itself (to advance its own checkpoint) and simply wasn't returning --
    # NOT a change to what this Agent does: it still never reads or
    # processes the content those events describe, it only now also
    # reports the events themselves, matching next_stage="ingest_and_ground"
    # already set on each one. A later stage (agents/ingestion_pipeline.py)
    # consumes this list; this Agent stays unaware that stage exists.
    change_events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self):
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "status": self.status,
            "source": self.source,
            "connection": self.connection,
            "capabilities": self.capabilities,
            "checkpoint": self.checkpoint,
            "skill_trace": [t.to_dict() for t in self.skill_trace],
            "error": self.error,
            "change_events": self.change_events,
        }


@dataclass
class SourceChangeEvent:
    event_id: str
    trace_id: str
    tenant_id: str
    source: Dict[str, Any]           # {adapter, kind, connection_handle}
    object: Dict[str, Any]           # {object_id, object_type, source_ref, version, content_hash, modified_at}
    change_type: str                 # created | updated | deleted | moved | permissions_changed | access_revoked
    checkpoint: Dict[str, Any]       # {previous_cursor, current_cursor}
    entitlement_state: str = "unknown"
    event_status: str = "detected"
    next_stage: str = "ingest_and_ground"
    error: Optional[Dict[str, Any]] = None

    def to_dict(self):
        return asdict(self)

    def idempotency_key(self) -> str:
        return "|".join([
            self.tenant_id,
            self.source.get("adapter", ""),
            self.object.get("object_id", ""),
            str(self.object.get("version")),
            self.change_type,
        ])
