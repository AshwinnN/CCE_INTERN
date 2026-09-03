#!/usr/bin/env python3
"""Live structured-ingestion demo against the local Postgres metadata store."""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env", override=True)

from agents.ingestion_workflow import run_ingestion  # noqa: E402
from repository.postgresql_metadata_repository import PostgreSQLMetadataRepository  # noqa: E402


def _demo_event() -> dict:
    return {
        "event_id": "demo-structured-1",
        "trace_id": "trc_demo_structured_ingestion",
        "tenant_id": "demo",
        "source": {"adapter": "snowflake", "kind": "structured", "connection_handle": "h1"},
        "object": {
            "object_id": "ANALYTICS.PUBLIC.ORDERS",
            "object_type": "table",
            "source_ref": "snowflake:ANALYTICS.PUBLIC.ORDERS",
            "version": "demo-v1",
            "content_hash": None,
            "modified_at": None,
        },
        "change_type": "created",
        "checkpoint": {"previous_cursor": None, "current_cursor": "demo-cur-1"},
        "entitlement_state": "unknown",
    }


def _demo_schema_card() -> dict:
    return {
        "schema": "PUBLIC",
        "tables": [
            {
                "name": "CUSTOMERS",
                "row_count": 3,
                "sample_row": {"CUSTOMER_ID": 1, "EMAIL": "ada@example.com"},
                "columns": [
                    {"name": "CUSTOMER_ID", "type": "NUMBER(18,0)", "nullable": False},
                    {"name": "EMAIL", "type": "VARCHAR(255)", "nullable": False},
                    {"name": "CREATED_AT", "type": "TIMESTAMP_NTZ", "nullable": False},
                ],
            },
            {
                "name": "ORDERS",
                "row_count": 7,
                "sample_row": {"ORDER_ID": 1001, "CUSTOMER_ID": 1, "TOTAL_AMOUNT": 42.50},
                "columns": [
                    {"name": "ORDER_ID", "type": "NUMBER(18,0)", "nullable": False},
                    {"name": "CUSTOMER_ID", "type": "NUMBER(18,0)", "nullable": False},
                    {"name": "TOTAL_AMOUNT", "type": "NUMBER(12,2)", "nullable": False},
                ],
            },
        ],
    }


def main() -> int:
    dsn = os.environ["CCE_METADATA_DATABASE_URL"]
    repo = PostgreSQLMetadataRepository(dsn)
    try:
        success, state = run_ingestion(
            _demo_event(),
            {"handle_id": "demo-h1"},
            source_id="snowflake-demo-account",
            schema_scope=["PUBLIC"],
            schema_database="ANALYTICS",
            fetch_structured_fn=lambda adapter, handle, scope: _demo_schema_card(),
            sdk_emit_fn=lambda payload: {"status": "demo_ok", "blocks": len(payload.get("blocks", []))},
            metadata_repository=repo,
        )
        if not success:
            raise RuntimeError(f"Ingestion failed: {state.get('errors')}")
        snapshot_id = state.get("metadata_snapshot_id")
        if not snapshot_id:
            raise RuntimeError(f"No metadata snapshot persisted. Warnings: {state.get('warnings')}")

        tables = repo.list_tables(snapshot_id)
        columns = repo.list_columns(snapshot_id)
        numeric_columns = repo.query_by_canonical_type("NUMERIC")

        print(f"Snapshot ID: {snapshot_id}")
        print(f"Tables persisted: {len(tables)}")
        print(f"Columns persisted: {len(columns)}")
        print(f"Numeric columns discoverable: {len(numeric_columns)}")

        if len(tables) != 2:
            raise RuntimeError(f"Expected 2 tables, found {len(tables)}")
        if len(columns) != 6:
            raise RuntimeError(f"Expected 6 columns, found {len(columns)}")
        if not any(col["column_name"] == "TOTAL_AMOUNT" for col in numeric_columns):
            raise RuntimeError("Expected TOTAL_AMOUNT to be queryable as NUMERIC")

        print("Live ingestion demo completed successfully.")
        return 0
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
