import uuid

from cce.integrations.agentic_plane.errors import GraphNotSupportedError
from cce.retrieval.service import RetrievalService


class LocalBoundary:
    def search(self, question, *, limit):
        return [
            {
                "memory_id": "chunk-1",
                "document_id": "doc-1",
                "chunk_text": "Grace Hopper developed COBOL.",
                "score": 0.88,
                "provenance": {
                    "source_id": "source-1",
                    "source_ref": "azure://docs/grace.txt",
                    "version": "v1",
                    "object_id": "grace.txt",
                    "trace_id": "ingest-trace-1",
                },
                "metadata": {"block_id": "block-1"},
            }
        ]

    def graph(self, question, *, depth, limit):
        raise GraphNotSupportedError("graph retrieval is unsupported on local")


def test_retrieve_returns_traceable_memories_and_explicit_local_graph_marker():
    service = RetrievalService(index_client=LocalBoundary(), backend="local")

    result = service.retrieve("Who developed COBOL?", limit=5, graph_depth=2)

    uuid.UUID(result["trace_id"])
    assert result["question"] == "Who developed COBOL?"
    assert result["backend"] == "local"
    assert result["memories"] == [
        {
            "memory_id": "chunk-1",
            "content": "Grace Hopper developed COBOL.",
            "score": 0.88,
            "provenance": {
                "document_id": "doc-1",
                "source_id": "source-1",
                "object_id": "grace.txt",
                "trace_id": "ingest-trace-1",
                "source_ref": "azure://docs/grace.txt",
                "version": "v1",
            },
            "metadata": {"block_id": "block-1"},
        }
    ]
    assert result["graph"] == {
        "unsupported": True,
        "backend": "local",
        "reason": "graph retrieval is unsupported on local",
    }
