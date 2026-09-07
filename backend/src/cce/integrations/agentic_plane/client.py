"""Real AgenticPlane SDK adapter behind CCE's integration boundary."""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from agenticplane import AgenticPlane
from agenticplane.types import MemoryType

from cce.integrations.agentic_plane.bridge import AgenticPlaneMemoryBridge
from cce.integrations.agentic_plane.chunking import payload_chunks
from cce.integrations.agentic_plane.errors import GraphExtractionError


logger = logging.getLogger(__name__)


class AgenticPlaneClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        dsn: str,
        timeout: int = 30,
        max_retries: int = 3,
        agent_id: str = "cce-ingestion",
        plane_factory: Callable[..., Any] | None = None,
        bridge_repository: Any | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("AgenticPlane base URL is required")
        if not api_key:
            raise ValueError("AgenticPlane API key is required")
        if not agent_id:
            raise ValueError("AgenticPlane agent ID is required")

        self._agent_id = agent_id
        factory = plane_factory or AgenticPlane
        self._plane = factory(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._bridge = (
            bridge_repository
            if bridge_repository is not None
            else AgenticPlaneMemoryBridge(dsn)
        )
        self._closed = False

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def index(self, payload: dict) -> dict:
        document_id = payload["document_id"]
        if payload.get("change_type") == "deleted":
            return self.delete(document_id)

        source_id = payload["source_id"]
        chunks = list(payload_chunks(payload))

        # AgenticPlane has no document-level replacement operation. Clear the
        # previous memory IDs recorded by CCE before storing the new revision.
        self.delete(document_id)
        if not chunks:
            return {
                "status": "indexed",
                "indexed": 0,
                "entities_extracted": 0,
                "relationships_extracted": 0,
            }

        provenance = {
            "document_id": document_id,
            "source_id": source_id,
            "object_id": payload.get("object_id") or document_id,
            "trace_id": payload.get("trace_id") or "",
            "source_ref": payload.get("source_ref") or document_id,
            "revision": payload.get("revision") or "",
        }
        items = [
            {
                "agent_id": self._agent_id,
                "content": chunk["chunk_text"],
                "memory_type": MemoryType.SEMANTIC,
                "metadata": {**provenance, **chunk.get("metadata", {})},
                "tags": ["ingested"],
                "extract_entities": False,
            }
            for chunk in chunks
        ]
        memory_ids = [str(memory_id) for memory_id in self._plane.memory.store_batch(items)]
        if len(memory_ids) != len(items):
            self._delete_new_memories(memory_ids)
            raise RuntimeError(
                "AgenticPlane store_batch returned %d memory IDs for %d chunks"
                % (len(memory_ids), len(items))
            )

        try:
            self._bridge.save_document(
                document_id=document_id,
                memory_ids=memory_ids,
                agent_id=self._agent_id,
                source_id=str(source_id),
                trace_id=payload.get("trace_id"),
            )
        except Exception:
            self._delete_new_memories(memory_ids)
            raise

        entity_count = 0
        relationship_count = 0
        for item, memory_id in zip(items, memory_ids):
            try:
                extraction = self._plane.graph.extract_and_store(
                    content=item["content"],
                    agent_id=self._agent_id,
                    memory_id=memory_id,
                )
            except Exception as exc:
                logger.exception(
                    "AgenticPlane graph extraction failed for memory_id=%s; "
                    "verify GRAPH_ENABLED=true and that ArcadeDB is running",
                    memory_id,
                )
                raise GraphExtractionError(
                    "AgenticPlane graph extraction failed for memory %s; verify "
                    "GRAPH_ENABLED=true and that ArcadeDB is running" % memory_id
                ) from exc
            entity_count += len(extraction.entities)
            relationship_count += len(extraction.relationships)

        return {
            "status": "indexed",
            "indexed": len(memory_ids),
            "entities_extracted": entity_count,
            "relationships_extracted": relationship_count,
        }

    def search(self, query: str, *, limit: int = 5) -> list[dict]:
        result = self._plane.memory.search(self._agent_id, query, limit=limit)
        # Boundary convention: score is cosine similarity, so higher is better.
        return [self._search_hit(record) for record in result.results]

    def delete(self, document_id: str) -> dict:
        references = self._bridge.list_document(document_id)
        for reference in references:
            self._plane.memory.delete(
                reference["memory_id"],
                reference["agent_id"],
            )
        if references:
            self._bridge.delete_document(document_id)
        return {"status": "deleted", "deleted": len(references)}

    def graph(
        self,
        query: str,
        *,
        agent_id: str | None = None,
        depth: int = 2,
        limit: int = 10,
    ) -> dict:
        result = self._plane.graph.graphrag_search(
            query,
            agent_id=agent_id or self._agent_id,
            depth=depth,
            limit=limit,
        )
        return {
            "entities": [_plain_sdk_model(item) for item in result.entities],
            "relationships": [
                _plain_sdk_model(item) for item in result.relationships
            ],
            "memories": [_plain_sdk_model(item) for item in result.memories],
        }

    def retrieve(self, question: str):
        """Compatibility alias for the currently stubbed runtime read seam."""
        return self.search(question)

    def close(self) -> None:
        if not self._closed:
            self._plane.close()
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def _delete_new_memories(self, memory_ids: list[str]) -> None:
        for memory_id in memory_ids:
            try:
                self._plane.memory.delete(memory_id, self._agent_id)
            except Exception:
                # Preserve the original persistence/count mismatch exception.
                pass

    @staticmethod
    def _search_hit(record: Any) -> dict:
        metadata = dict(record.metadata or {})
        source_id = metadata.get("source_id")
        return {
            "memory_id": str(record.memory_id),
            "document_id": metadata.get("document_id"),
            "chunk_text": record.content,
            "source_id": source_id,
            "score": float(record.score),
            "provenance": {
                "source_id": source_id,
                "source_ref": metadata.get("source_ref"),
                "version": metadata.get("revision", metadata.get("version", "")),
                "object_id": metadata.get("object_id"),
                "trace_id": metadata.get("trace_id"),
            },
            "metadata": metadata,
        }


def _plain_sdk_model(value: Any) -> dict:
    """Convert an SDK model to a plain mapping without inventing fields."""
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if model_dump is not None:
        return dict(model_dump(mode="json"))
    return {
        key: item
        for key, item in vars(value).items()
        if not key.startswith("_")
    }
