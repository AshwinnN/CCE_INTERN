from types import SimpleNamespace
from uuid import uuid4

from cce.governance.models import Workspace
from cce.http.app import create_app
from cce.runtime.models import QueryResponse, WorkspaceInfo
from cce.sources.models import IngestionRunResult
from fastapi.testclient import TestClient

TRACE_ID = str(uuid4())
RUN_ID = str(uuid4())
WORKSPACE_UUID = uuid4()
WORKSPACE_ID = "Test_workspace"
ADMIN = {"actor_id": "admin", "roles": ["ADMIN"]}

WORKSPACE = Workspace(
    workspace_uuid=WORKSPACE_UUID,
    workspace_id=WORKSPACE_ID,
    name="Test",
    created_by="admin",
)


def test_http_adapter_health_workspace_sources_and_query():
    app_context = SimpleNamespace(
        ready=True,
        workspace_repository=SimpleNamespace(
            list=lambda: [WORKSPACE],
            create=lambda body, actor: WORKSPACE,
            get=lambda workspace_id: WORKSPACE,
        ),
        source_service=SimpleNamespace(
            list_sources=lambda wid: [
                {
                    "source_id": "source-123",
                    "source_type": "snowflake",
                    "name": "Production Snowflake",
                    "kind": "structured",
                    "credential_ref": "env://X",
                    "config": {"schema": "PUBLIC"},
                    "enabled": True,
                    "created_at": None,
                    "updated_at": None,
                }
            ],
            register_source=lambda wid, **kwargs: {
                "source_id": "source-123",
                "status": "REGISTERED",
            },
            test_connection=lambda wid, resource_id: {
                "source_id": resource_id,
                "status": "SUCCESS",
            },
            trigger_ingestion=lambda wid, resource_id: IngestionRunResult(
                ingestion_run_id=RUN_ID,
                status="RUNNING",
                objects_processed=0,
                objects_failed=0,
            ),
            get_ingestion_status=lambda wid, run_id: IngestionRunResult(
                ingestion_run_id=run_id,
                status="SUCCESS",
                objects_processed=1,
                objects_failed=0,
            ),
        ),
        query_service=SimpleNamespace(
            query=lambda request: QueryResponse(
                trace_id=TRACE_ID,
                status="SUCCESS",
                question=request.question,
                workspace=WorkspaceInfo(
                    workspace_uuid=WORKSPACE_UUID,
                    workspace_id=WORKSPACE_ID,
                    name="Test",
                ),
                package={"name": "Test_package", "version": 1},
                answer="ok",
            )
        ),
        feedback_service=SimpleNamespace(
            submit=lambda wid, request, actor: {"status": "RECORDED"}
        ),
        index_client=SimpleNamespace(
            search=lambda question, limit, metadata_filter: [
                {
                    "memory_id": "m1",
                    "score": 0.9,
                    "chunk_text": "hit",
                    "metadata": {"workspace_uuid": str(WORKSPACE_UUID), "source_id": "source-123"},
                }
            ]
        ),
    )
    client = TestClient(create_app(app_context))

    assert client.get("/health").json() == {"status": "SERVING"}
    assert [w["workspace_id"] for w in client.get("/workspaces").json()] == [WORKSPACE_ID]
    assert client.post(
        "/workspaces", json={"name": "Test", "actor": ADMIN}
    ).json()["workspace_id"] == WORKSPACE_ID
    assert client.get(f"/workspaces/{WORKSPACE_ID}").json()["workspace_id"] == WORKSPACE_ID

    scope = f"/workspaces/{WORKSPACE_ID}"
    assert client.post(
        scope + "/sources",
        json={
            "name": "Production Snowflake",
            "source_type": "snowflake",
            "credential_ref": "env://X",
            "config": {"schema": "PUBLIC"},
            "actor": ADMIN,
        },
    ).json() == {"source_id": "source-123", "status": "REGISTERED"}
    assert client.get(scope + "/sources").json()[0]["name"] == "Production Snowflake"
    assert client.post(scope + "/sources/source-123/test", json={"actor": ADMIN}).json() == {
        "source_id": "source-123",
        "status": "SUCCESS",
    }
    ingest = client.post(scope + "/sources/source-123/ingest", json={"actor": ADMIN}).json()
    assert ingest["ingestion_run_id"] == RUN_ID and ingest["status"] == "RUNNING"
    assert client.get(scope + f"/ingestion-runs/{RUN_ID}").json()["status"] == "SUCCESS"

    response = client.post(scope + "/query", json={"question": "hello"})
    assert response.status_code == 200
    assert response.json()["answer"] == "ok"
    assert response.json()["trace_id"] == TRACE_ID

    retrieved = client.post(
        scope + "/retrieve", json={"question": "Who worked on CCE?", "actor": ADMIN}
    ).json()
    assert retrieved and retrieved[0]["memory_id"] == "m1"

    feedback = client.post(
        scope + "/feedback",
        json={"trace_id": TRACE_ID, "rating": "GOOD", "actor": ADMIN},
    )
    assert feedback.status_code == 200

    app_context.source_service.list_sources = lambda wid: []
    empty_response = client.get(scope + "/sources")
    assert empty_response.status_code == 200
    assert empty_response.json() == []
