"""Raw AgenticPlane memory + GraphRAG retrieval proof."""

from __future__ import annotations

import uuid

from cce.integrations.agentic_plane.errors import GraphNotSupportedError


class RetrievalService:
    """Retrieve provider records without governance or answer synthesis."""

    def __init__(self, *, index_client, backend: str) -> None:
        self._index_client = index_client
        self._backend = backend

    def retrieve(
        self,
        question: str,
        *,
        limit: int = 10,
        graph_depth: int = 2,
    ) -> dict:
        trace_id = str(uuid.uuid4())
        memories = [
            _retrieved_memory(hit)
            for hit in self._index_client.search(question, limit=limit)
        ]
        try:
            graph = self._index_client.graph(
                question,
                depth=graph_depth,
                limit=limit,
            )
        except GraphNotSupportedError as exc:
            graph = {
                "unsupported": True,
                "backend": self._backend,
                "reason": str(exc),
            }
        return {
            "trace_id": trace_id,
            "question": question,
            "backend": self._backend,
            "memories": memories,
            "graph": graph,
        }


def _retrieved_memory(hit: dict) -> dict:
    provenance = hit["provenance"]
    return {
        "memory_id": hit["memory_id"],
        "content": hit["chunk_text"],
        "score": hit["score"],
        "provenance": {
            "document_id": hit["document_id"],
            "source_id": provenance.get("source_id"),
            "object_id": provenance.get("object_id"),
            "trace_id": provenance.get("trace_id"),
            "source_ref": provenance.get("source_ref"),
            "version": provenance.get("version"),
        },
        "metadata": hit.get("metadata", {}),
    }
