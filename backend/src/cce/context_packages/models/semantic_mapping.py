"""Semantic mapping model."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticMapping:
    concept: str
    physical_ref: str
