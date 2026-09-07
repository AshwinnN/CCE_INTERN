#!/usr/bin/env python3
"""Guarded live AgenticPlane ingest/search/delete integration smoke test."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time
import uuid

import psycopg2
from dotenv import load_dotenv

from cce.config.settings import load_settings
from cce.integrations.agentic_plane.client import AgenticPlaneClient
from cce.persistence.postgres.migrations import initialize_control_postgres


REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=False)
    load_dotenv(REPO_ROOT / "backend" / ".env", override=False)
    required = ("CCE_AGENTICPLANE_BASE_URL", "CCE_AGENTICPLANE_API_KEY")
    missing = [name for name in required if not os.environ.get(name)]
    if os.environ.get("CCE_INDEX_BACKEND", "").strip().lower() != "agentic_plane":
        print("SKIP: set CCE_INDEX_BACKEND=agentic_plane for the live smoke test")
        return 0
    if missing:
        print("SKIP: missing " + ", ".join(missing))
        return 0

    settings = load_settings()
    initialize_control_postgres(
        settings.database_url,
        timeout_seconds=settings.postgres_wait_timeout_seconds,
    )

    token = uuid.uuid4().hex
    document_id = "cce-agentic-plane-smoke-%s" % token
    source_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    phrase = "CCE AgenticPlane smoke marker %s" % token
    client = AgenticPlaneClient(
        base_url=settings.agenticplane_base_url,
        api_key=settings.agenticplane_api_key,
        timeout=settings.agenticplane_timeout,
        max_retries=settings.agenticplane_max_retries,
        agent_id=settings.agenticplane_agent_id,
        dsn=settings.database_url,
    )
    deleted = False
    try:
        result = client.index(
            {
                "document_id": document_id,
                "source_id": source_id,
                "source_ref": "smoke://%s" % document_id,
                "revision": "smoke-v1",
                "object_id": "%s.txt" % document_id,
                "trace_id": trace_id,
                "blocks": [
                    {"id": "smoke-block-1", "type": "paragraph", "text": phrase}
                ],
            }
        )
        if result != {"status": "indexed", "indexed": 1}:
            raise RuntimeError("unexpected index result: %r" % result)
        if _bridge_count(settings.database_url, document_id) != 1:
            raise RuntimeError("bridge row was not persisted")

        hit = _wait_for_hit(client, phrase, document_id)
        if not 0.0 <= hit["score"] <= 1.0:
            raise RuntimeError("unexpected similarity score: %r" % hit["score"])
        provenance = hit["provenance"]
        if provenance["source_id"] != source_id or provenance["trace_id"] != trace_id:
            raise RuntimeError("provenance did not round-trip: %r" % provenance)

        delete_result = client.delete(document_id)
        deleted = True
        if delete_result != {"status": "deleted", "deleted": 1}:
            raise RuntimeError("unexpected delete result: %r" % delete_result)
        if _bridge_count(settings.database_url, document_id) != 0:
            raise RuntimeError("bridge row was not removed")
        if any(
            row["document_id"] == document_id
            for row in client.search(phrase, limit=20)
        ):
            raise RuntimeError("deleted AgenticPlane memory is still searchable")

        print("PASS: live ingest, bridge persistence, search, provenance, and delete")
        return 0
    finally:
        if not deleted:
            try:
                client.delete(document_id)
            except Exception:
                pass
        client.close()


def _bridge_count(dsn: str, document_id: str) -> int:
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM cce_agentic_plane_memory WHERE document_id = %s",
                (document_id,),
            )
            return int(cur.fetchone()[0])


def _wait_for_hit(client: AgenticPlaneClient, phrase: str, document_id: str) -> dict:
    for _ in range(5):
        hits = client.search(phrase, limit=20)
        for hit in hits:
            if hit["document_id"] == document_id:
                return hit
        time.sleep(1)
    raise RuntimeError("stored AgenticPlane memory was not returned by search")


if __name__ == "__main__":
    sys.exit(main())
