"""PostgreSQL source repository for minimal source registration."""

from __future__ import annotations

import uuid

import psycopg2
import psycopg2.extras


_CCE_UUID_NAMESPACE = uuid.UUID("6f1b1a2e-6c1a-4b8e-9f2a-9e3b7c2d5a10")


class PostgresSourceRepository:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def save_source(
        self,
        adapter: str,
        source_id: str,
        credential_ref: str | None = None,
        kind: str | None = None,
        config: dict | None = None,
        enabled: bool = True,
    ) -> str:
        stable_id = str(
            uuid.uuid5(_CCE_UUID_NAMESPACE, f"rpc-source:{adapter}:{source_id}")
        )
        with psycopg2.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cce_source (
                        source_id, adapter, account_id, kind, credential_ref, config, enabled, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (adapter, account_id)
                    DO UPDATE SET
                        kind = EXCLUDED.kind,
                        credential_ref = EXCLUDED.credential_ref,
                        config = EXCLUDED.config,
                        enabled = EXCLUDED.enabled,
                        updated_at = now()
                    RETURNING source_id
                    """,
                    (
                        stable_id,
                        adapter,
                        source_id,
                        kind,
                        credential_ref,
                        psycopg2.extras.Json(config or {}),
                        enabled,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
        return str(row[0])

    def get_source(self, source_id: str) -> dict | None:
        with psycopg2.connect(self._dsn) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT source_id, adapter, account_id, kind, credential_ref, config, enabled
                    FROM cce_source
                    WHERE source_id::text = %s OR account_id = %s
                    LIMIT 1
                    """,
                    (source_id, source_id),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def create_ingestion_run(self, source_id: str, trace_id: str | None = None) -> str:
        run_id = str(uuid.uuid4())
        source = self.get_source(source_id)
        if source is None:
            raise KeyError("source %r is not registered" % source_id)
        with psycopg2.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cce_ingestion_run (run_id, source_id, status, trace_id)
                    VALUES (%s, %s, 'RUNNING', %s)
                    """,
                    (run_id, source["source_id"], trace_id),
                )
                conn.commit()
        return run_id

    def update_ingestion_run(
        self,
        run_id: str,
        status: str,
        *,
        objects_processed: int = 0,
        objects_failed: int = 0,
        error_message: str | None = None,
    ) -> None:
        with psycopg2.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE cce_ingestion_run
                    SET status = %s,
                        finished_at = CASE WHEN %s IN ('SUCCESS', 'FAILED') THEN now() ELSE finished_at END,
                        objects_processed = %s,
                        objects_failed = %s,
                        error_message = %s
                    WHERE run_id = %s
                    """,
                    (
                        status,
                        status,
                        objects_processed,
                        objects_failed,
                        error_message,
                        run_id,
                    ),
                )
                conn.commit()

    def get_ingestion_run(self, run_id: str) -> dict | None:
        with psycopg2.connect(self._dsn) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT run_id, source_id, status, started_at, finished_at,
                           objects_processed, objects_failed, error_message, trace_id
                    FROM cce_ingestion_run
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None
