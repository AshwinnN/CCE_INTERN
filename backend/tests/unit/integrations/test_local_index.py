import uuid

from cce.integrations.agentic_plane.local_index import LocalIndexClient


class FakeCursor:
    def __init__(self):
        self.rows = [
            {
                "document_id": "doc-1",
                "chunk_text": "alpha searchable text",
                "source_id": str(uuid.uuid4()),
                "source_ref": "file:///doc-1.txt",
                "version": "v1",
                "object_id": "doc-1.txt",
                "trace_id": "trace-1",
                "metadata": {"block_id": "b1"},
                "distance": 0.1,
            }
        ]
        self.executed = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self, *args, **kwargs):
        return self.cursor_obj

    def commit(self):
        pass


def test_local_index_indexes_blocks_and_searches_with_provenance(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        "cce.integrations.agentic_plane.local_index.psycopg2.connect",
        lambda dsn: connection,
    )
    source_id = str(uuid.uuid4())
    client = LocalIndexClient(
        "postgresql://test",
        embed_texts=lambda texts: [[0.1] * 768 for _ in texts],
    )

    result = client.index(
        {
            "document_id": "doc-1",
            "source_id": source_id,
            "source_ref": "file:///doc-1.txt",
            "revision": "v1",
            "object_id": "doc-1.txt",
            "trace_id": "trace-1",
            "blocks": [{"id": "b1", "type": "paragraph", "text": "alpha searchable text"}],
        }
    )
    assert result == {"status": "indexed", "indexed": 1}

    rows = client.search("alpha", limit=1)
    assert rows[0]["chunk_text"] == "alpha searchable text"
    assert rows[0]["source_id"] == rows[0]["provenance"]["source_id"]
    assert rows[0]["score"] == 0.9
    assert rows[0]["provenance"]["source_ref"] == "file:///doc-1.txt"
    assert rows[0]["provenance"]["version"] == "v1"
    assert rows[0]["provenance"]["object_id"] == "doc-1.txt"
