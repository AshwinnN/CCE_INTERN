#!/usr/bin/env python3
"""Abstractions for deterministic object/document source connectors."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional


@dataclass
class SourceConnection:
    connector: "SourceConnector"
    connection_id: str
    source_id: str
    adapter: str
    read_only_verified: bool = True
    entitlement_capture_verified: bool = True
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


class SourceConnector(ABC):
    """Pure contract for unstructured sources such as Drive, Slack, or Blob."""

    @abstractmethod
    def connect(self) -> SourceConnection:
        """Establish a read-only source connection and return a safe handle."""

    @abstractmethod
    def list_objects(self, cursor: Optional[str] = None) -> Dict:
        """Return changed object metadata without fetching content."""

    @abstractmethod
    def fetch_object(self, object_id: str) -> bytes:
        """Fetch object content bytes by source object id."""

    @abstractmethod
    def close(self) -> None:
        """Release source resources. Idempotent."""
