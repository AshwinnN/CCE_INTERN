"""PostgresSourceRepository against real workspace-scoped schema."""
import pytest
from cce.persistence.postgres.source_repository import PostgresSourceRepository
from test_lifecycle import ADMIN
from cce.governance.models import WorkspaceCreate


def test_source_crud_and_ingestion_run_are_workspace_scoped(system):
    s = system
    repo = PostgresSourceRepository(s.db.dsn)
    workspace = s.workspaces.create(WorkspaceCreate(name="Source repo test"), ADMIN)
    other = s.workspaces.create(WorkspaceCreate(name="Other workspace"), ADMIN)

    saved = repo.save_source(
        workspace.workspace_uuid,
        "Production Blob",
        "azure_blob",
        "azure-kv://blob",
        "unstructured",
        {"authentication": "connection_string", "container": "documents"},
    )
    assert saved["name"] == "Production Blob"
    assert saved["config"]["container"] == "documents"

    fetched = repo.get_source(workspace.workspace_uuid, saved["source_id"])
    assert fetched["source_id"] == saved["source_id"]
    with pytest.raises(KeyError):
        repo.get_source(other.workspace_uuid, saved["source_id"])

    listed = repo.list_sources(workspace.workspace_uuid)
    assert len(listed) == 1 and listed[0]["source_id"] == saved["source_id"]
    assert repo.list_sources(other.workspace_uuid) == []

    updated = repo.update(workspace.workspace_uuid, saved["source_id"], {"name": "Renamed Blob"})
    assert updated["name"] == "Renamed Blob"
    with pytest.raises(KeyError):
        repo.update(other.workspace_uuid, saved["source_id"], {"name": "Should fail"})

    run_id = s.ingestion.create_or_resume(saved["source_id"]).ingestion_run_id
    run = repo.get_ingestion_run(workspace.workspace_uuid, run_id)
    assert str(run["run_id"]) == str(run_id)
    with pytest.raises(KeyError):
        repo.get_ingestion_run(other.workspace_uuid, run_id)

    archived = repo.archive(workspace.workspace_uuid, saved["source_id"])
    assert archived["archived_at"] is not None and archived["enabled"] is False
