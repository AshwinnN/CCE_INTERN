from types import SimpleNamespace

from cce.integrations.agentic_plane.client import AgenticPlaneClient


class FakeMemory:
    def __init__(self):
        self.stored_items = []
        self.deleted = []
        self.search_calls = []
        self.search_result = SimpleNamespace(results=[])

    def store_batch(self, items):
        self.stored_items = items
        return ["memory-%d" % index for index in range(len(items))]

    def delete(self, memory_id, agent_id):
        self.deleted.append((memory_id, agent_id))
        return True

    def search(self, agent_id, query, *, limit):
        self.search_calls.append((agent_id, query, limit))
        return self.search_result


class FakePlane:
    def __init__(self):
        self.memory = FakeMemory()
        self.closed = False

    def close(self):
        self.closed = True


class FakeBridge:
    def __init__(self):
        self.documents = {}
        self.saved = []
        self.deleted = []

    def list_document(self, document_id):
        return list(self.documents.get(document_id, []))

    def save_document(self, **kwargs):
        self.saved.append(kwargs)
        self.documents[kwargs["document_id"]] = [
            {
                "document_id": kwargs["document_id"],
                "chunk_index": index,
                "memory_id": memory_id,
                "agent_id": kwargs["agent_id"],
            }
            for index, memory_id in enumerate(kwargs["memory_ids"])
        ]

    def delete_document(self, document_id):
        rows = self.documents.pop(document_id, [])
        self.deleted.append(document_id)
        return len(rows)


def _client(plane, bridge, constructor_calls=None):
    def factory(**kwargs):
        if constructor_calls is not None:
            constructor_calls.append(kwargs)
        return plane

    return AgenticPlaneClient(
        base_url="https://plane.example",
        api_key="ap_secret",
        timeout=17,
        max_retries=4,
        agent_id="cce-ingestion",
        dsn="postgresql://unused",
        plane_factory=factory,
        bridge_repository=bridge,
    )


def test_index_maps_raw_chunks_and_provenance_and_persists_ids():
    plane = FakePlane()
    bridge = FakeBridge()
    constructor_calls = []
    client = _client(plane, bridge, constructor_calls)
    payload = {
        "document_id": "doc-1",
        "source_id": "0f6df234-b57b-48b5-9ba5-a47d8de7a64d",
        "source_ref": "azure://container/doc-1.csv",
        "revision": "rev-7",
        "object_id": "doc-1.csv",
        "trace_id": "trc_10e64f9d5b2c4a9eb5dcf31fac4dbe19",
        "blocks": [
            {
                "id": "block-1",
                "type": "table",
                "text": "raw block text",
                "cells": [{"text": "raw cell text", "row": 2, "col": 3}],
            }
        ],
    }

    result = client.index(payload)

    assert constructor_calls == [
        {
            "api_key": "ap_secret",
            "base_url": "https://plane.example",
            "timeout": 17,
            "max_retries": 4,
        }
    ]
    assert result == {"status": "indexed", "indexed": 2}
    assert [item["content"] for item in plane.memory.stored_items] == [
        "raw block text",
        "raw cell text",
    ]
    assert all("embedding" not in item for item in plane.memory.stored_items)
    assert all(item["memory_type"].value == "semantic" for item in plane.memory.stored_items)
    assert all(item["extract_entities"] is False for item in plane.memory.stored_items)
    assert all(item["tags"] == ["ingested"] for item in plane.memory.stored_items)

    block_metadata = plane.memory.stored_items[0]["metadata"]
    assert block_metadata == {
        "document_id": "doc-1",
        "source_id": payload["source_id"],
        "object_id": "doc-1.csv",
        "trace_id": payload["trace_id"],
        "source_ref": "azure://container/doc-1.csv",
        "revision": "rev-7",
        "block_id": "block-1",
        "type": "table",
    }
    assert plane.memory.stored_items[1]["metadata"]["row"] == 2
    assert plane.memory.stored_items[1]["metadata"]["col"] == 3
    assert bridge.saved == [
        {
            "document_id": "doc-1",
            "memory_ids": ["memory-0", "memory-1"],
            "agent_id": "cce-ingestion",
            "source_id": payload["source_id"],
            "trace_id": payload["trace_id"],
        }
    ]


def test_reindex_and_deleted_payload_delete_each_bridged_memory():
    plane = FakePlane()
    bridge = FakeBridge()
    bridge.documents["doc-1"] = [
        {"memory_id": "old-1", "agent_id": "original-agent"},
        {"memory_id": "old-2", "agent_id": "original-agent"},
    ]
    client = _client(plane, bridge)

    result = client.index(
        {
            "document_id": "doc-1",
            "source_id": "source-1",
            "blocks": [{"id": "b1", "type": "text", "text": "replacement"}],
        }
    )

    assert result == {"status": "indexed", "indexed": 1}
    assert plane.memory.deleted[:2] == [
        ("old-1", "original-agent"),
        ("old-2", "original-agent"),
    ]
    assert bridge.deleted == ["doc-1"]

    result = client.index({"document_id": "doc-1", "change_type": "deleted"})
    assert result == {"status": "deleted", "deleted": 1}
    assert plane.memory.deleted[-1] == ("memory-0", "cce-ingestion")
    assert bridge.deleted == ["doc-1", "doc-1"]


def test_search_maps_memory_record_to_backend_neutral_shape():
    plane = FakePlane()
    bridge = FakeBridge()
    plane.memory.search_result = SimpleNamespace(
        results=[
            SimpleNamespace(
                content="matched raw text",
                score=0.91,
                metadata={
                    "document_id": "doc-1",
                    "source_id": "source-1",
                    "source_ref": "file:///doc-1.txt",
                    "revision": "v2",
                    "object_id": "doc-1.txt",
                    "trace_id": "trace-1",
                    "block_id": "b1",
                    "type": "paragraph",
                },
            )
        ]
    )
    client = _client(plane, bridge)

    hits = client.search("matched", limit=3)

    assert plane.memory.search_calls == [("cce-ingestion", "matched", 3)]
    assert hits == [
        {
            "document_id": "doc-1",
            "chunk_text": "matched raw text",
            "source_id": "source-1",
            "score": 0.91,
            "provenance": {
                "source_id": "source-1",
                "source_ref": "file:///doc-1.txt",
                "version": "v2",
                "object_id": "doc-1.txt",
                "trace_id": "trace-1",
            },
            "metadata": plane.memory.search_result.results[0].metadata,
        }
    ]

    client.close()
    client.close()
    assert plane.closed is True
