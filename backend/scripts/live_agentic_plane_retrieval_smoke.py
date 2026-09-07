"""Guarded live Azure Blob -> CCE ingestion -> AgenticPlane retrieval smoke.

Run this only against a CCE server configured with
``CCE_INDEX_BACKEND=agentic_plane``. The script never sends or persists the
AgenticPlane API key; it checks the variable only as an explicit live-test
guard. The CCE server resolves the Azure credential reference itself.
"""

from __future__ import annotations

import os
import sys
import time
import uuid

import requests


REQUIRED_ENV = (
    "CCE_AGENTICPLANE_BASE_URL",
    "CCE_AGENTICPLANE_API_KEY",
    "CCE_AZURE_BLOB_CONNECTION_STRING",
    "CCE_AZURE_BLOB_CONTAINER",
    "CCE_AGENTICPLANE_GRAPH_SMOKE_QUESTION",
)


def main() -> int:
    if os.environ.get("CCE_LIVE_AGENTICPLANE_GRAPH_SMOKE", "").lower() != "true":
        print("SKIPPED: set CCE_LIVE_AGENTICPLANE_GRAPH_SMOKE=true to run")
        return 0
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        print("SKIPPED: missing " + ", ".join(missing))
        return 0

    base_url = os.environ.get("CCE_HTTP_BASE_URL", "http://localhost:8080").rstrip("/")
    container = os.environ["CCE_AZURE_BLOB_CONTAINER"]
    prefix = os.environ.get("CCE_AZURE_BLOB_PREFIX", "")
    source_id = os.environ.get("CCE_AGENTICPLANE_GRAPH_SMOKE_SOURCE_ID") or str(
        uuid.uuid5(uuid.NAMESPACE_URL, "cce-live-graph:%s:%s" % (container, prefix))
    )
    timeout = int(os.environ.get("CCE_AGENTICPLANE_GRAPH_SMOKE_TIMEOUT", "300"))
    configured_credential = os.environ["CCE_AZURE_BLOB_CONNECTION_STRING"]
    credential_ref = (
        configured_credential
        if configured_credential.startswith(("azure-kv://", "env://"))
        else "env://CCE_AZURE_BLOB_CONNECTION_STRING"
    )

    registered = _post(
        base_url + "/sources",
        {
            "adapter": "azure-blob",
            "source_id": source_id,
            "credential_ref": credential_ref,
            "kind": "unstructured",
            "config": {"container": container, "prefix": prefix},
        },
    )
    _require_status(registered, "REGISTERED", "source registration")
    connected = _post(base_url + "/sources/%s/test" % source_id, {})
    _require_status(connected, "CONNECTED", "Azure Blob connection")

    triggered = _post(base_url + "/sources/%s/ingest" % source_id, {})
    run_id = triggered.get("ingestion_run_id")
    if not run_id:
        raise RuntimeError("ingestion did not return an ingestion_run_id: %r" % triggered)
    deadline = time.monotonic() + timeout
    status = triggered
    while status.get("status") == "RUNNING" and time.monotonic() < deadline:
        time.sleep(2)
        status = _get(base_url + "/ingestion-runs/%s" % run_id)
    _require_status(status, "SUCCESS", "ingestion")

    retrieved = _post(
        base_url + "/retrieve",
        {
            "question": os.environ["CCE_AGENTICPLANE_GRAPH_SMOKE_QUESTION"],
            "limit": 10,
            "graph_depth": 2,
        },
    )
    uuid.UUID(retrieved["trace_id"])
    if retrieved.get("backend") != "agentic_plane":
        raise RuntimeError("CCE is not using agentic_plane: %r" % retrieved.get("backend"))
    matching = [
        item
        for item in retrieved.get("memories", [])
        if item.get("provenance", {}).get("source_id") == source_id
    ]
    if not matching:
        raise RuntimeError("retrieve returned no memory from source %s" % source_id)
    graph = retrieved.get("graph") or {}
    if graph.get("unsupported"):
        raise RuntimeError("hosted graph was reported unsupported: %r" % graph)
    if not graph.get("entities") or not graph.get("relationships"):
        raise RuntimeError(
            "GraphRAG returned no entity/relationship pair; use source content and a "
            "question with an explicit relationship: %r" % graph
        )
    memory_ids = {item["memory_id"] for item in matching}
    if not any(
        memory_ids.intersection(entity.get("source_memories", []))
        for entity in graph["entities"]
    ):
        raise RuntimeError("graph entities do not reference a retrieved source memory")

    print(
        "PASS: source=%s run=%s memories=%d entities=%d relationships=%d trace=%s"
        % (
            source_id,
            run_id,
            len(matching),
            len(graph["entities"]),
            len(graph["relationships"]),
            retrieved["trace_id"],
        )
    )
    return 0


def _post(url: str, payload: dict) -> dict:
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def _get(url: str) -> dict:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def _require_status(payload: dict, expected: str, operation: str) -> None:
    if payload.get("status") != expected:
        raise RuntimeError("%s failed: %r" % (operation, payload))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("FAILED: %s" % exc, file=sys.stderr)
        raise
