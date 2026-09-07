"""CCE-owned references to memories stored by AgenticPlane."""

from __future__ import annotations

import uuid

import psycopg2
import psycopg2.extras


class AgenticPlaneMemoryBridge:
    """Persist document-to-memory references in the CCE control database."""

    def __init__(self, dsn: str):
        if not dsn:
            raise ValueError("AgenticPlane memory bridge requires a PostgreSQL DSN")
        self._dsn = dsn

    def list_document(self, document_id: str) -> list[dict]:
        with psycopg2.connect(self._dsn) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT document_id, chunk_index, memory_id, agent_id,
                           source_id::text AS source_id, trace_id::text AS trace_id
                    FROM cce_agentic_plane_memory
                    WHERE document_id = %s
                    ORDER BY chunk_index
                    """,
                    (document_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def save_document(
        self,
        *,
        document_id: str,
        memory_ids: list[str],
        agent_id: str,
        source_id: str | None,
        trace_id: str | None,
    ) -> None:
        rows = [
            (
                document_id,
                chunk_index,
                str(memory_id),
                agent_id,
                _uuid_or_none(source_id),
                _uuid_or_none(trace_id),
            )
            for chunk_index, memory_id in enumerate(memory_ids)
        ]
        if not rows:
            return
        with psycopg2.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO cce_agentic_plane_memory (
                        document_id, chunk_index, memory_id, agent_id, source_id, trace_id
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    rows,
                )
            conn.commit()

    def delete_document(self, document_id: str) -> int:
        with psycopg2.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM cce_agentic_plane_memory WHERE document_id = %s",
                    (document_id,),
                )
                deleted = cur.rowcount
            conn.commit()
        return deleted


def _uuid_or_none(value: str | None) -> str | None:
    if not value:
        return None
    candidate = str(value)
    if candidate.startswith("trc_"):
        candidate = candidate[4:]
    try:
        return str(uuid.UUID(candidate))
    except ValueError:
        return None
