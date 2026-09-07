from types import SimpleNamespace

import pytest

from cce.ingestion.checkpoint import IngestionCheckpointStore
from cce.ingestion.models import (
    CanonicalDocument,
    ElementType,
    ProcessingResult,
    ProcessingStatus,
    TextElement,
)
from cce.ingestion.orchestrator import run_ingestion
from cce.ingestion.parsers.factory import ParserFactory
from cce.integrations.agentic_plane.client import AgenticPlaneClient


class FakeParser:
    def parse(self, path, metadata):
        return ProcessingResult(
            status=ProcessingStatus.SUCCESS,
            document=CanonicalDocument(
                metadata=metadata,
                elements=[
                    TextElement(
                        id="block-1",
                        type=ElementType.TEXT,
                        text="Grace Hopper created COBOL for the United States Navy.",
                    )
                ],
            ),
        )


class FakeMemory:
    def __init__(self):
        self.items = []

    def store_batch(self, items):
        self.items.extend(items)
        return ["memory-1"]

    def delete(self, memory_id, agent_id):
        return True


class FakeGraph:
    def __init__(self):
        self.extractions = []

    def extract_and_store(self, **kwargs):
        self.extractions.append(kwargs)
        return SimpleNamespace(entities=[object()], relationships=[object()])


class FakeBridge:
    def list_document(self, document_id):
        return []

    def save_document(self, **kwargs):
        self.saved = kwargs

    def delete_document(self, document_id):
        return 0


@pytest.mark.parametrize("mime_type", sorted(ParserFactory._registry))
def test_every_registered_mime_runs_through_memory_and_graph(
    mime_type, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "cce.ingestion.change_detection.file_detection.detect_mime_type",
        lambda path: mime_type,
    )
    monkeypatch.setitem(ParserFactory._registry, mime_type, FakeParser)
    plane = SimpleNamespace(memory=FakeMemory(), graph=FakeGraph(), close=lambda: None)
    client = AgenticPlaneClient(
        base_url="https://plane.example",
        api_key="ap_test",
        dsn="postgresql://unused",
        plane_factory=lambda **kwargs: plane,
        bridge_repository=FakeBridge(),
    )
    event = {
        "event_id": "event-1",
        "trace_id": "trace-1",
        "tenant_id": None,
        "source": {"adapter": "azure-blob", "kind": "unstructured"},
        "object": {
            "object_id": "sample.bin",
            "object_type": "document",
            "source_ref": "azure://container/sample.bin",
            "version": "v1",
        },
        "change_type": "created",
        "checkpoint": {"previous_cursor": None, "current_cursor": "cursor-1"},
        "entitlement_state": "unknown",
    }

    success, state = run_ingestion(
        event,
        {"connection_id": "test"},
        source_id="source-1",
        fetch_unstructured_fn=lambda adapter, handle, object_id: b"file bytes",
        sdk_emit_fn=client.index,
        checkpoint_store=IngestionCheckpointStore(str(tmp_path)),
    )

    assert success, state["errors"]
    assert len(plane.memory.items) == 1
    assert plane.memory.items[0]["content"].startswith("Grace Hopper")
    assert plane.memory.items[0]["extract_entities"] is False
    assert plane.graph.extractions == [
        {
            "content": plane.memory.items[0]["content"],
            "agent_id": "cce-ingestion",
            "memory_id": "memory-1",
        }
    ]
