#!/usr/bin/env python3
"""Live Azure Blob unstructured-ingestion demo.

Fetches one target blob through the ingestion pipeline and writes the first
five parsed elements to temp/data/log_<timestamp>.txt. The SDK emit remains
a dry-run/captured payload because the downstream service is not implemented.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND / "src"))
load_dotenv(REPO / ".env", override=True)
load_dotenv(BACKEND / ".env", override=True)

from cce.connectors.agent import ConnectorAgent  # noqa: E402
from cce.connectors.contracts import ConnectorRequest  # noqa: E402
from cce.ingestion.service import run_pipeline  # noqa: E402
from cce.connectors.fetch import azure_blob_fetcher  # noqa: E402
from cce.ingestion.normalizers.unstructured_document_exporter import to_structured_content_json  # noqa: E402


TARGET_BLOB = "noaa_data/national-202607.pdf"


def _object_lister(cursor):
    return {
        "objects": [
            {
                "object_id": TARGET_BLOB,
                "revision": "demo-v1",
                "scope": "container:%s/%s" % (os.environ["CCE_AZURE_BLOB_CONTAINER"], TARGET_BLOB),
                "state": "added",
            }
        ],
        "cursor_next": "azure-demo-cur-1",
    }


def _make_request() -> ConnectorRequest:
    return ConnectorRequest.from_dict({
        "tenant_id": os.environ.get("CCE_TENANT_ID", "demo"),
        "source_adapter": "azure-blob",
        "credential_ref": "env://CCE_AZURE_BLOB_CONNECTION_STRING",
        "request_id": "azure-blob-demo-1",
        "requested_capabilities": ["content_fetch", "change_detection"],
        "source_scope": {
            "source_id": "azure-blob-noaa-demo",
            "object_scope": ["container:%s/%s" % (os.environ["CCE_AZURE_BLOB_CONTAINER"], TARGET_BLOB)],
            "max_objects": 1,
        },
        "observation": {"mode": "start"},
    })


def _write_first_elements(log_path: Path, result, emitted_payloads):
    outcome = result.ingestion_results[0] if result.ingestion_results else None
    payload = emitted_payloads[0] if emitted_payloads else {}
    elements = payload.get("blocks", [])
    parsed_json = to_structured_content_json(
        {"metadata": payload.get("metadata", {}), "elements": elements},
        max_content_items=5,
    )

    lines = [
        "Azure Blob unstructured ingestion demo",
        "timestamp=%s" % datetime.now().isoformat(timespec="seconds"),
        "target_blob=%s" % TARGET_BLOB,
        "connector_status=%s" % result.connector_response.status,
        "checkpoint=%s" % result.connector_response.checkpoint,
        "ingestion_success=%s" % (outcome.success if outcome else None),
        "ingestion_errors=%s" % (outcome.errors if outcome else []),
        "ingestion_warnings=%s" % (outcome.warnings if outcome else []),
        "element_count=%s" % len(elements),
        "",
        "Parsed JSON (first 5 content items):",
        json.dumps(parsed_json, indent=2, ensure_ascii=False, default=str),
        "",
        "First 5 canonical blocks:",
    ]

    for idx, element in enumerate(elements[:5], start=1):
        text = element.get("text", "")
        if not text and element.get("cells"):
            text = " | ".join(cell.get("text", "") for cell in element.get("cells", [])[:8])
        preview = text.replace("\r", " ").replace("\n", " ")[:1000]
        lines.extend([
            "",
            "Element #%d" % idx,
            json.dumps({
                "id": element.get("id"),
                "type": element.get("type"),
                "page_number": element.get("page_number"),
                "order": element.get("order"),
                "text_preview": preview,
            }, indent=2, default=str),
        ])

    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    required = ("CCE_AZURE_BLOB_CONNECTION_STRING", "CCE_AZURE_BLOB_CONTAINER")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing required .env values: %s" % ", ".join(missing))

    emitted_payloads = []
    fetcher = azure_blob_fetcher(
        os.environ["CCE_AZURE_BLOB_CONNECTION_STRING"],
        os.environ["CCE_AZURE_BLOB_CONTAINER"],
    )
    agent = ConnectorAgent(object_lister=_object_lister)
    result = run_pipeline(
        _make_request(),
        connector_agent=agent,
        fetch_unstructured_fn=fetcher,
        sdk_emit_fn=lambda payload: emitted_payloads.append(payload) or {
            "status": "captured",
            "blocks": len(payload.get("blocks", [])),
        },
    )

    log_dir = REPO / "_temp" / "data"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / ("log_%s.txt" % timestamp)
    _write_first_elements(log_path, result, emitted_payloads)

    outcome = result.ingestion_results[0] if result.ingestion_results else None
    print("Connector status: %s" % result.connector_response.status)
    print("Ingestion success: %s" % (outcome.success if outcome else None))
    print("Parsed element count: %s" % (len(emitted_payloads[0].get("blocks", [])) if emitted_payloads else 0))
    print("Log written: %s" % log_path)
    if outcome and not outcome.success:
        print("Errors: %s" % outcome.errors)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
