"""Lineage attached to context assets."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Provenance:
    source_id: str
    source_ref: str
    version: str | None = None
