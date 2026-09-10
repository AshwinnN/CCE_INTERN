from types import SimpleNamespace
from uuid import uuid4

import pytest
from cce.ingestion.lifecycle_models import IngestionRunStatus
from cce.sources.service import SourceService

WORKSPACE = uuid4()


class InMemorySourceRepo:
    def __init__(self):
        self.sources = {}

    def save_source(self, workspace_uuid, name, source_type, credential_ref, kind, config):
        source_id = str(uuid4())
        self.sources[source_id] = {
            "source_id": source_id,
            "workspace_uuid": workspace_uuid,
            "name": name,
            "source_type": source_type,
            "credential_ref": credential_ref,
            "kind": kind,
            "config": config,
            "enabled": True,
            "archived_at": None,
        }
        return self.sources[source_id]

    def list_sources(self, workspace_uuid):
        return [s for s in self.sources.values() if s["workspace_uuid"] == workspace_uuid]

    def get_source(self, workspace_uuid, source_id):
        source = self.sources.get(source_id)
        if not source or source["workspace_uuid"] != workspace_uuid:
            raise KeyError("Source not found")
        return source


class InMemoryIngestionRepo:
    def __init__(self):
        self.runs = {}

    def create_or_resume(self, source_id):
        run = SimpleNamespace(
            ingestion_run_id=uuid4(),
            status=IngestionRunStatus.RUNNING,
            objects_processed=0,
            objects_failed=0,
        )
        self.runs[source_id] = run
        return run


def build_service(source_repository=None, ingestion_repository=None):
    return SourceService(
        source_repository=source_repository or InMemorySourceRepo(),
        metadata_repository=None,
        checkpoint_store=None,
        index_client=None,
        ingestion_repository=ingestion_repository or InMemoryIngestionRepo(),
    )


def test_register_source_validates_config_and_derives_kind():
    repo = InMemorySourceRepo()
    service = build_service(source_repository=repo)
    saved = service.register_source(
        WORKSPACE,
        name="Production Blob",
        source_type="azure_blob",
        credential_ref="azure-kv://blob",
        config={"authentication": "connection_string", "container": "documents"},
    )
    assert saved["kind"] == "unstructured"
    assert service.list_sources(WORKSPACE) == [saved]


def test_register_source_rejects_missing_name_or_credential():
    service = build_service()
    with pytest.raises(ValueError):
        service.register_source(
            WORKSPACE,
            name="",
            source_type="azure_blob",
            credential_ref="azure-kv://blob",
            config={"authentication": "connection_string", "container": "documents"},
        )
    with pytest.raises(ValueError):
        service.register_source(
            WORKSPACE,
            name="Production Blob",
            source_type="azure_blob",
            credential_ref="",
            config={"authentication": "connection_string", "container": "documents"},
        )


def test_register_source_rejects_invalid_config():
    service = build_service()
    with pytest.raises(Exception):
        service.register_source(
            WORKSPACE,
            name="Production Blob",
            source_type="azure_blob",
            credential_ref="azure-kv://blob",
            config={"authentication": "service_principal", "container": "documents"},
        )


def test_test_connection_uses_built_connector(monkeypatch):
    repo = InMemorySourceRepo()
    service = build_service(source_repository=repo)
    saved = service.register_source(
        WORKSPACE,
        name="Production Blob",
        source_type="azure_blob",
        credential_ref="azure-kv://blob",
        config={"authentication": "connection_string", "container": "documents"},
    )
    connected = SimpleNamespace(connect=lambda: None, close=lambda: None)
    monkeypatch.setattr(service, "_build_connector", lambda source: connected)
    result = service.test_connection(WORKSPACE, saved["source_id"])
    assert result == {"source_id": saved["source_id"], "status": "SUCCESS"}


def test_test_connection_propagates_connector_failure(monkeypatch):
    repo = InMemorySourceRepo()
    service = build_service(source_repository=repo)
    saved = service.register_source(
        WORKSPACE,
        name="Production Blob",
        source_type="azure_blob",
        credential_ref="azure-kv://blob",
        config={"authentication": "connection_string", "container": "documents"},
    )

    def fail_to_build(_source):
        raise ValueError("invalid Azure Blob configuration")

    monkeypatch.setattr(service, "_build_connector", fail_to_build)
    with pytest.raises(ValueError, match="invalid Azure Blob configuration"):
        service.test_connection(WORKSPACE, saved["source_id"])


def test_disabled_source_blocks_test_and_ingest():
    repo = InMemorySourceRepo()
    service = build_service(source_repository=repo)
    saved = service.register_source(
        WORKSPACE,
        name="Production Blob",
        source_type="azure_blob",
        credential_ref="azure-kv://blob",
        config={"authentication": "connection_string", "container": "documents"},
    )
    repo.sources[saved["source_id"]]["enabled"] = False
    with pytest.raises(ValueError):
        service.test_connection(WORKSPACE, saved["source_id"])
    with pytest.raises(ValueError):
        service.trigger_ingestion(WORKSPACE, saved["source_id"])


def test_trigger_ingestion_creates_or_resumes_a_run():
    repo = InMemorySourceRepo()
    ingestion = InMemoryIngestionRepo()
    service = build_service(source_repository=repo, ingestion_repository=ingestion)
    saved = service.register_source(
        WORKSPACE,
        name="Production Blob",
        source_type="azure_blob",
        credential_ref="azure-kv://blob",
        config={"authentication": "connection_string", "container": "documents"},
    )
    result = service.trigger_ingestion(WORKSPACE, saved["source_id"])
    assert result.status == "RUNNING"
    assert saved["source_id"] in ingestion.runs
