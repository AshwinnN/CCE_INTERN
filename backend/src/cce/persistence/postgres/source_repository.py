"""PostgreSQL source repository for minimal source registration."""

from __future__ import annotations

import uuid

import psycopg2


_CCE_UUID_NAMESPACE = uuid.UUID("6f1b1a2e-6c1a-4b8e-9f2a-9e3b7c2d5a10")


class PostgresSourceRepository:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def save_source(
        self, adapter: str, source_id: str, credential_ref: str | None = None
    ) -> str:
        stable_id = str(
            uuid.uuid5(_CCE_UUID_NAMESPACE, f"rpc-source:{adapter}:{source_id}")
        )
        with psycopg2.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cce_source (
                        source_id, adapter, account_id, display_name
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (adapter, account_id)
                    DO UPDATE SET display_name = EXCLUDED.display_name
                    RETURNING source_id
                    """,
                    (stable_id, adapter, source_id, credential_ref),
                )
                row = cur.fetchone()
                conn.commit()
        return str(row[0])
