"""Governance trace event models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TraceEvent:
    trace_id: str
    event_type: str
    actor_id: str | None = None
