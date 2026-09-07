"""CCE-side AgenticPlane boundary contract."""

from __future__ import annotations

from typing import Protocol


class AgenticPlaneBoundary(Protocol):
    def index(self, payload: dict) -> dict:
        """Index normalized ingestion payload."""

    def search(self, query: str, *, limit: int = 5) -> list[dict]:
        """Search indexed content."""

    def delete(self, document_id: str) -> dict:
        """Delete indexed content for a document."""

    def graph(
        self,
        query: str,
        *,
        agent_id: str | None = None,
        depth: int = 2,
        limit: int = 10,
    ) -> dict:
        """Return backend-neutral GraphRAG data for a natural-language query."""
