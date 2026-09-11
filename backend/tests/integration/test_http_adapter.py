from types import SimpleNamespace
from uuid import uuid4

from cce.http.app import create_app
from cce.runtime.models import DomainResolution, QueryBranchResult, QueryResponse
from cce.sources.models import IngestionRunResult, SourceOperationResult
from fastapi.testclient import TestClient

TRACE_ID = str(uuid4())
RUN_ID = str(uuid4())


def test_http_adapter_health_sources_and_query():
    app_context = SimpleNamespace(
        ready=True,
        source_service=SimpleNamespace(
            list_sources=lambda: [
                {
                    "source_id": "source-123",
                    "adapter": "snowflake",
                    "account_id": "abc",
                    "kind": "structured",
                    "credential_ref": "env://X",
                    "config": {"schema": "PUBLIC"},
                    "enabled": True,
                    "created_at": None,
                    "updated_at": None,
                }
            ],
            register_source=lambda adapter, source_id, credential_ref, kind, config: (
                SourceOperationResult(
                    source_id="source-123", status="REGISTERED", error=None
                )
            ),
            test_connection=lambda source_id: SourceOperationResult(
                source_id=source_id, status="CONNECTED", error=None
            ),
            trigger_ingestion=lambda source_id: IngestionRunResult(
                ingestion_run_id=RUN_ID,
                status="RUNNING",
                error=None,
                objects_processed=0,
                objects_failed=0,
            ),
            get_ingestion_status=lambda run_id: IngestionRunResult(
                ingestion_run_id=run_id,
                status="COMPLETE",
                error=None,
                objects_processed=1,
                objects_failed=0,
            ),
        ),
        query_service=SimpleNamespace(
            query=lambda request: QueryResponse(
                trace_id=TRACE_ID,
                question=request.question,
                domain=DomainResolution(),
                context_on=QueryBranchResult(status="SUCCESS", answer="ok"),
                context_off=QueryBranchResult(status="SKIPPED"),
            )
        ),
        retrieval_service=SimpleNamespace(
            retrieve=lambda question, limit, graph_depth: {
                "trace_id": "retrieve-trace-1",
                "question": question,
                "backend": "agentic_plane",
                "memories": [],
                "graph": {"entities": [], "relationships": [], "memories": []},
            }
        ),
        governance_service=SimpleNamespace(),
        package_service=SimpleNamespace(),
    )
    client = TestClient(create_app(app_context))

    assert client.get("/health").json() == {"status": "SERVING"}
    assert client.post(
        "/sources",
        json={
            "adapter": "snowflake",
            "source_id": "abc",
            "credential_ref": "env://X",
            "kind": "structured",
            "config": {"schema": "PUBLIC"},
        },
    ).json() == {"source_id": "source-123", "status": "REGISTERED"}
    assert client.get("/sources").json() == [
        {
            "source_id": "source-123",
            "adapter": "snowflake",
            "account_id": "abc",
            "kind": "structured",
            "credential_ref": "env://X",
            "config": {"schema": "PUBLIC"},
            "enabled": True,
            "created_at": None,
            "updated_at": None,
        }
    ]
    assert client.post("/sources/source-123/test", json={}).json() == {
        "source_id": "source-123",
        "status": "CONNECTED",
    }
    assert client.post("/sources/source-123/ingest", json={}).json() == {
        "ingestion_run_id": RUN_ID,
        "status": "RUNNING",
        "objects_processed": 0,
        "objects_failed": 0,
    }
    assert client.get(f"/ingestion-runs/{RUN_ID}").json() == {
        "ingestion_run_id": RUN_ID,
        "status": "COMPLETE",
        "objects_processed": 1,
        "objects_failed": 0,
    }
    response = client.post("/query", json={"question": "hello"})
    assert response.status_code == 200
    assert response.json()["context_on"]["answer"] == "ok"
    assert response.json()["trace_id"] == TRACE_ID
    assert response.json()["context_off"]["status"] == "SKIPPED"
    assert client.post(
        "/retrieve",
        json={"question": "Who worked on CCE?", "limit": 7, "graph_depth": 3},
    ).json() == {
        "trace_id": "retrieve-trace-1",
        "question": "Who worked on CCE?",
        "backend": "agentic_plane",
        "memories": [],
        "graph": {"entities": [], "relationships": [], "memories": []},
    }

    app_context.source_service.list_sources = lambda: []
    empty_response = client.get("/sources")
    assert empty_response.status_code == 200
    assert empty_response.json() == []
