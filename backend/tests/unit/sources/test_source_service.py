import time

from cce.sources.service import SourceService


class InMemoryRepo:
    def __init__(self):
        self.sources = {}
        self.runs = {}

    def save_source(self, adapter, source_id, credential_ref, kind, config, enabled):
        saved_id = "00000000-0000-0000-0000-000000000001"
        self.sources[saved_id] = {
            "source_id": saved_id,
            "adapter": adapter,
            "account_id": source_id,
            "credential_ref": credential_ref,
            "kind": kind,
            "config": config,
            "enabled": enabled,
        }
        self.sources[source_id] = self.sources[saved_id]
        return saved_id

    def get_source(self, source_id):
        return self.sources.get(source_id)

    def list_sources(self):
        unique_sources = {source["source_id"]: source for source in self.sources.values()}
        return list(unique_sources.values())

    def create_ingestion_run(self, source_id, trace_id=None):
        self.runs["run-1"] = {
            "run_id": "run-1",
            "source_id": source_id,
            "status": "RUNNING",
            "objects_processed": 0,
            "objects_failed": 0,
            "error_message": None,
            "trace_id": trace_id,
        }
        return "run-1"

    def update_ingestion_run(self, run_id, status, objects_processed=0, objects_failed=0, error_message=None):
        self.runs[run_id].update(
            {
                "status": status,
                "objects_processed": objects_processed,
                "objects_failed": objects_failed,
                "error_message": error_message,
            }
        )

    def get_ingestion_run(self, run_id):
        return self.runs.get(run_id)


class FakeIndex:
    def __init__(self):
        self.payloads = []

    def index(self, payload):
        self.payloads.append(payload)
        return {"status": "indexed", "indexed": len(payload.get("blocks", []))}


class MemoryCheckpoint:
    def save(self, source_id, object_id, state):
        return "checkpoint-1"


def test_source_service_local_fs_ingestion_reaches_pipeline(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "hello.txt").write_text("searchable synthetic content", encoding="utf-8")

    repo = InMemoryRepo()
    index = FakeIndex()
    service = SourceService(
        source_repository=repo,
        metadata_repository=None,
        checkpoint_store=MemoryCheckpoint(),
        index_client=index,
        run_async=False,
    )
    registered = service.register_source(
        adapter="local-fs",
        source_id="docs",
        credential_ref="",
        kind="unstructured",
        config={"root_path": str(root), "password": "must-not-leak"},
    )

    assert service.list_sources() == [
        {
            "source_id": registered.source_id,
            "adapter": "local-fs",
            "account_id": "docs",
            "kind": "unstructured",
            "credential_ref": None,
            "config": {"root_path": str(root), "password": "[REDACTED]"},
            "enabled": True,
            "created_at": None,
            "updated_at": None,
        }
    ]

    assert service.test_connection(registered.source_id).status == "CONNECTED"
    result = service.trigger_ingestion(registered.source_id)
    assert result.status == "SUCCESS"
    assert result.objects_processed == 1
    assert index.payloads[0]["blocks"][0]["text"] == "searchable synthetic content"
    assert index.payloads[0]["source_ref"].endswith("hello.txt")
