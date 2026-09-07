from types import SimpleNamespace

from fastapi.testclient import TestClient

from cce.http.app import create_app
from cce.runtime.service import QueryResponse


def test_http_adapter_health_sources_and_query():
    app_context = SimpleNamespace(
        ready=True,
        source_service=SimpleNamespace(
            register_source=lambda adapter, source_id, credential_ref, kind, config: SimpleNamespace(
                source_id="source-123", status="REGISTERED", error=None
            ),
            test_connection=lambda source_id: SimpleNamespace(
                source_id=source_id, status="CONNECTED", error=None
            ),
            trigger_ingestion=lambda source_id: SimpleNamespace(
                ingestion_run_id="run-1",
                status="RUNNING",
                error=None,
                objects_processed=0,
                objects_failed=0,
            ),
            get_ingestion_status=lambda run_id: SimpleNamespace(
                ingestion_run_id=run_id,
                status="SUCCESS",
                error=None,
                objects_processed=1,
                objects_failed=0,
            ),
        ),
        query_service=SimpleNamespace(
            query=lambda request: QueryResponse(
                answer="ok",
                trace_id="trace-1",
                context_used=True,
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
    assert client.post("/sources/source-123/test", json={}).json() == {
        "source_id": "source-123",
        "status": "CONNECTED",
    }
    assert client.post("/sources/source-123/ingest", json={}).json() == {
        "ingestion_run_id": "run-1",
        "status": "RUNNING",
        "objects_processed": 0,
        "objects_failed": 0,
    }
    assert client.get("/ingestion-runs/run-1").json() == {
        "ingestion_run_id": "run-1",
        "status": "SUCCESS",
        "objects_processed": 1,
        "objects_failed": 0,
    }
    assert client.post("/query", json={"question": "hello"}).json() == {
        "answer": "ok",
        "trace_id": "trace-1",
        "citations": [],
        "context_used": True,
        "applied_rule": "",
        "package_id": "",
        "package_version": "",
        "executed_sql": "",
        "approver": "",
        "valid_until": "",
        "confidence": 0.0,
    }
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
