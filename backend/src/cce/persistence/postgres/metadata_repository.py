#!/usr/bin/env python3
"""PostgreSQL implementation of cce.persistence.ports.MetadataRepository, backed
by schema/*.sql.

Deviates from CCE_STRUCTURED_METADATA_IMPLEMENTATION_PROMPT.md's own sketch
in three ways, each matching an existing convention elsewhere in this repo
rather than the prompt's literal code:

1. `psycopg2`, not `asyncpg` -- this package is synchronous throughout (see
   repository/base.py's module docstring); asyncpg would be the only async
   dependency anywhere in the codebase.
2. table_id/column_id/constraint_id/relationship_id are `uuid.uuid5`-derived
   from a stable natural key (schema_id+table_name, table_id+column_name,
   ...), not a fresh random UUID per row. The SAME id then identifies the
   SAME table/column across every snapshot it appears in, which is what
   makes ON CONFLICT (id, snapshot_id) DO UPDATE SET updated_at = now() an
   actual idempotent-retry mechanism instead of a dead clause, and lets
   tools/schema_change_detector.py diff two snapshots by id instead of by
   name.
3. `ensure_source`/`ensure_namespace`/`ensure_schema` exist at all -- the
   prompt's save_table()/save_column() assume a schema_id is already in
   hand; something has to create the source -> namespace -> schema chain
   the first time a source is ever ingested, and repository/base.py is the
   natural owner of that (get-or-create, one round trip via
   INSERT ... ON CONFLICT ... DO UPDATE ... RETURNING).
"""
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool

from cce.persistence.ports import MetadataRepository, SchemaChange, SchemaSnapshot

# Fixed namespace UUID this module's uuid5 ids are derived under -- any
# constant UUID works, it just has to never change (changing it would
# silently mint new ids for every existing table/column on next deploy).
_CCE_UUID_NAMESPACE = uuid.UUID("6f1b1a2e-6c1a-4b8e-9f2a-9e3b7c2d5a10")


def _stable_uuid(*parts: str) -> str:
    return str(uuid.uuid5(_CCE_UUID_NAMESPACE, ":".join(str(p) for p in parts)))


class PostgreSQLMetadataRepository(MetadataRepository):

    def __init__(self, dsn: str, minconn: int = 1, maxconn: int = 5):
        self._pool = psycopg2.pool.SimpleConnectionPool(minconn, maxconn, dsn)

    @contextmanager
    def _cursor(self):
        conn = self._pool.getconn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    # ----- hierarchy (get-or-create) -----

    def ensure_source(self, adapter: str, account_id: str,
                       display_name: Optional[str] = None) -> str:
        source_id = _stable_uuid("source", adapter, account_id)
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO cce_source (source_id, adapter, account_id, display_name)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (adapter, account_id)
                DO UPDATE SET display_name = COALESCE(EXCLUDED.display_name, cce_source.display_name)
                RETURNING source_id
                """,
                (source_id, adapter, account_id, display_name),
            )
            return str(cur.fetchone()["source_id"])

    def ensure_namespace(self, source_id: str, namespace_name: str, namespace_type: str) -> str:
        namespace_id = _stable_uuid("namespace", source_id, namespace_name)
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO cce_namespace (namespace_id, source_id, namespace_name, namespace_type)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (source_id, namespace_name) DO UPDATE SET namespace_type = EXCLUDED.namespace_type
                RETURNING namespace_id
                """,
                (namespace_id, source_id, namespace_name, namespace_type),
            )
            return str(cur.fetchone()["namespace_id"])

    def ensure_schema(self, namespace_id: str, schema_name: str) -> str:
        schema_id = _stable_uuid("schema", namespace_id, schema_name)
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO cce_schema (schema_id, namespace_id, schema_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (namespace_id, schema_name) DO UPDATE SET schema_name = EXCLUDED.schema_name
                RETURNING schema_id
                """,
                (schema_id, namespace_id, schema_name),
            )
            return str(cur.fetchone()["schema_id"])

    # ----- snapshots -----

    def save_snapshot(self, snapshot: SchemaSnapshot) -> str:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO cce_schema_snapshot (
                    snapshot_id, source_id, schema_id, captured_at, schema_hash,
                    status, table_count, column_count, error_detail
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING snapshot_id
                """,
                (snapshot.snapshot_id, snapshot.source_id, snapshot.schema_id,
                 snapshot.captured_at, snapshot.schema_hash, snapshot.status,
                 snapshot.table_count, snapshot.column_count, snapshot.error_detail),
            )
            return str(cur.fetchone()["snapshot_id"])

    def latest_snapshot_id(self, schema_id: str) -> Optional[str]:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT snapshot_id FROM cce_schema_snapshot
                WHERE schema_id = %s AND status IN ('SUCCESS', 'PARTIAL')
                ORDER BY captured_at DESC LIMIT 1
                """,
                (schema_id,),
            )
            row = cur.fetchone()
            return str(row["snapshot_id"]) if row else None

    # ----- tables / columns -----

    def save_table(self, table_record: Dict[str, Any]) -> str:
        table_id = _stable_uuid("table", table_record["schema_id"], table_record["table_name"])
        now = datetime.now(timezone.utc)
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO cce_table (
                    table_id, snapshot_id, schema_id, table_name, table_type,
                    description, row_count, is_temporary, metadata, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (table_id, snapshot_id) DO UPDATE SET updated_at = EXCLUDED.updated_at
                RETURNING table_id
                """,
                (table_id, table_record["snapshot_id"], table_record["schema_id"],
                 table_record["table_name"], table_record.get("table_type", "TABLE"),
                 table_record.get("description"), table_record.get("row_count"),
                 table_record.get("is_temporary", False),
                 psycopg2.extras.Json(table_record.get("metadata", {})), now, now),
            )
            return str(cur.fetchone()["table_id"])

    def save_column(self, column_record: Dict[str, Any]) -> str:
        column_id = _stable_uuid("column", column_record["table_id"], column_record["column_name"])
        now = datetime.now(timezone.utc)
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO cce_column (
                    column_id, snapshot_id, table_id, column_name, ordinal_position,
                    data_type, type_detail, native_data_type, is_nullable,
                    numeric_precision, numeric_scale, character_maximum_length,
                    description, metadata, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (column_id, snapshot_id) DO UPDATE SET updated_at = EXCLUDED.updated_at
                RETURNING column_id
                """,
                (column_id, column_record["snapshot_id"], column_record["table_id"],
                 column_record["column_name"], column_record["ordinal_position"],
                 column_record["data_type"],
                 psycopg2.extras.Json(column_record.get("type_detail", {})),
                 column_record["native_data_type"], column_record.get("is_nullable", True),
                 column_record.get("numeric_precision"), column_record.get("numeric_scale"),
                 column_record.get("character_maximum_length"), column_record.get("description"),
                 psycopg2.extras.Json(column_record.get("metadata", {})), now, now),
            )
            return str(cur.fetchone()["column_id"])

    def list_tables(self, snapshot_id: str) -> List[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM cce_table WHERE snapshot_id = %s ORDER BY table_name", (snapshot_id,))
            return [dict(row) for row in cur.fetchall()]

    def list_columns(self, snapshot_id: str, table_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._cursor() as cur:
            if table_id:
                cur.execute(
                    """SELECT * FROM cce_column WHERE snapshot_id = %s AND table_id = %s
                       ORDER BY ordinal_position""",
                    (snapshot_id, table_id))
            else:
                cur.execute(
                    "SELECT * FROM cce_column WHERE snapshot_id = %s ORDER BY table_id, ordinal_position",
                    (snapshot_id,))
            return [dict(row) for row in cur.fetchall()]

    def query_by_canonical_type(self, data_type: str, source_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                """
                WITH latest_snapshot AS (
                    SELECT DISTINCT ON (schema_id) schema_id, snapshot_id
                    FROM cce_schema_snapshot
                    WHERE status IN ('SUCCESS', 'PARTIAL') AND schema_id IS NOT NULL
                      AND (%(source_id)s IS NULL OR source_id = %(source_id)s)
                    ORDER BY schema_id, captured_at DESC
                )
                SELECT c.column_id, c.column_name, c.data_type, c.type_detail,
                       c.native_data_type, t.table_id, t.table_name, s.schema_name
                FROM cce_column c
                JOIN cce_table t ON t.table_id = c.table_id AND t.snapshot_id = c.snapshot_id
                JOIN latest_snapshot ls ON ls.snapshot_id = c.snapshot_id
                JOIN cce_schema s ON s.schema_id = t.schema_id
                WHERE c.data_type = %(data_type)s
                ORDER BY t.table_name, c.ordinal_position
                """,
                {"data_type": data_type, "source_id": source_id},
            )
            return [dict(row) for row in cur.fetchall()]

    # ----- constraints / relationships -----

    def save_constraint(self, constraint_record: Dict[str, Any]) -> str:
        constraint_id = _stable_uuid(
            "constraint", constraint_record["table_id"], constraint_record["constraint_name"])
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO cce_constraint (
                    constraint_id, snapshot_id, table_id, constraint_name,
                    constraint_type, column_names, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (constraint_id, snapshot_id) DO NOTHING
                RETURNING constraint_id
                """,
                (constraint_id, constraint_record["snapshot_id"], constraint_record["table_id"],
                 constraint_record["constraint_name"], constraint_record["constraint_type"],
                 psycopg2.extras.Json(constraint_record.get("column_names", [])),
                 psycopg2.extras.Json(constraint_record.get("metadata", {}))),
            )
            row = cur.fetchone()
            return str(row["constraint_id"]) if row else constraint_id

    def save_relationship(self, relationship_record: Dict[str, Any]) -> str:
        relationship_id = _stable_uuid(
            "relationship", relationship_record["source_table_id"],
            relationship_record["target_table_id"], relationship_record.get("constraint_name") or "")
        snapshot_id = relationship_record["snapshot_id"]
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO cce_relationship (
                    relationship_id, snapshot_id, source_table_id, target_table_id,
                    relationship_type, constraint_name, confidence, description
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (relationship_id, snapshot_id) DO NOTHING
                """,
                (relationship_id, snapshot_id, relationship_record["source_table_id"],
                 relationship_record["target_table_id"], relationship_record["relationship_type"],
                 relationship_record.get("constraint_name"), relationship_record.get("confidence", 1.0),
                 relationship_record.get("description")),
            )
            for ordinal, mapping in enumerate(relationship_record.get("column_mappings", [])):
                cur.execute(
                    """
                    INSERT INTO cce_relationship_column_mapping (
                        relationship_id, snapshot_id, ordinal_position, source_column_id, target_column_id
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (relationship_id, snapshot_id, ordinal_position) DO NOTHING
                    """,
                    (relationship_id, snapshot_id, ordinal,
                     mapping["source_column_id"], mapping["target_column_id"]),
                )
        return relationship_id

    # ----- change detection -----

    def detect_changes(self, snapshot_1: str, snapshot_2: str) -> List[SchemaChange]:
        """Table-level diff only (added/removed) -- see
        tools/schema_change_detector.SchemaChangeDetector for the
        comprehensive version (tables + columns) most callers should use."""
        changes: List[SchemaChange] = []
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT table_name, table_id FROM cce_table WHERE snapshot_id = %s
                  AND table_id NOT IN (SELECT table_id FROM cce_table WHERE snapshot_id = %s)
                """,
                (snapshot_2, snapshot_1),
            )
            for row in cur.fetchall():
                changes.append(SchemaChange("TABLE_ADDED", row["table_name"],
                                             detail={"table_id": str(row["table_id"])}))

            cur.execute(
                """
                SELECT table_name, table_id FROM cce_table WHERE snapshot_id = %s
                  AND table_id NOT IN (SELECT table_id FROM cce_table WHERE snapshot_id = %s)
                """,
                (snapshot_1, snapshot_2),
            )
            for row in cur.fetchall():
                changes.append(SchemaChange("TABLE_REMOVED", row["table_name"],
                                             detail={"table_id": str(row["table_id"])}))
        return changes

    def close(self) -> None:
        if self._pool and not self._pool.closed:
            self._pool.closeall()
