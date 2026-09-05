from types import SimpleNamespace

from fastapi.testclient import TestClient

from cce.http.app import create_app
from cce.runtime.service import QueryResponse


def test_http_adapter_health_sources_and_query():
    app_context = SimpleNamespace(
        ready=True,
        source_repository=SimpleNamespace(
            save_source=lambda adapter, source_id, credential_ref: "source-123"
        ),
        query_service=SimpleNamespace(
            query=lambda request: QueryResponse(
                answer="ok",
                trace_id="trace-1",
                context_used=True,
            )
        ),
        governance_service=SimpleNamespace(),
        package_service=SimpleNamespace(),
    )
    client = TestClient(create_app(app_context))

    assert client.get("/health").json() == {"status": "SERVING"}
    assert client.post(
        "/sources",
        json={"adapter": "snowflake", "source_id": "abc", "credential_ref": "env://X"},
    ).json() == {"source_id": "source-123", "status": "REGISTERED"}
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
