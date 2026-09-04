#!/usr/bin/env python3
"""Live Snowflake structured-ingestion demo into local Postgres metadata.

Uses CCE_SNOWFLAKE_* for source config and CCE_CONTROL_DATABASE_URL for the
Postgres metadata repository. The SDK emit is captured locally because the
downstream SDK endpoint is optional/not implemented for this demo.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND / "src"))
load_dotenv(REPO / ".env", override=True)
load_dotenv(BACKEND / ".env", override=True)

from cce.ingestion.orchestrator import run_ingestion  # noqa: E402
from cce.connectors.factory import ConnectorFactory  # noqa: E402
from cce.connectors.structured.snowflake.config import build_config_from_env  # noqa: E402
from cce.persistence.postgres.metadata_repository import PostgreSQLMetadataRepository  # noqa: E402


def _event(config) -> dict:
    object_id = "%s.%s" % (config.database, config.schema)
    return {
        "event_id": "live-snowflake-structured-1",
        "trace_id": "trc_live_snowflake_structured_ingestion",
        "tenant_id": os.environ.get("CCE_TENANT_ID", "demo"),
        "source": {"adapter": "snowflake", "kind": "structured", "connection_handle": "live-snowflake"},
        "object": {
            "object_id": object_id,
            "object_type": "schema",
            "source_ref": "snowflake:%s" % object_id,
            "version": "live",
            "content_hash": None,
            "modified_at": None,
        },
        "change_type": "created",
        "checkpoint": {"previous_cursor": None, "current_cursor": "live"},
        "entitlement_state": "unknown",
    }


def _max_tables():
    value = os.environ.get("CCE_SNOWFLAKE_MAX_TABLES")
    return int(value) if value else None


def _snowflake_information_schema_fetcher(max_tables=None):
    def fetcher(_adapter, _connection_handle, schema_scope):
        schema = schema_scope[0] if schema_scope else os.environ["CCE_SNOWFLAKE_SCHEMA"]
        config = build_config_from_env(schema=schema)
        connector = ConnectorFactory.create(config)
        connector.connect()
        try:
            return connector.get_information_schema_card(schema, max_tables=max_tables)
        finally:
            connector.close()

    return fetcher


def main() -> int:
    required = (
        "CCE_SNOWFLAKE_ACCOUNT",
        "CCE_SNOWFLAKE_USER",
        "CCE_SNOWFLAKE_PRIVATE_KEY",
        "CCE_SNOWFLAKE_DATABASE",
        "CCE_SNOWFLAKE_SCHEMA",
        "CCE_CONTROL_DATABASE_URL",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing required .env values: %s" % ", ".join(missing))

    config = build_config_from_env()
    repo = PostgreSQLMetadataRepository(
        os.environ.get("CCE_CONTROL_DATABASE_URL") or os.environ["CCE_METADATA_DATABASE_URL"]
    )
    emitted_payloads = []
    try:
        success, state = run_ingestion(
            _event(config),
            {"handle_id": "live-snowflake"},
            source_id="snowflake-%s" % config.account_id,
            schema_scope=[config.schema],
            schema_database=config.database,
            fetch_structured_fn=_snowflake_information_schema_fetcher(max_tables=_max_tables()),
            sdk_emit_fn=lambda payload: emitted_payloads.append(payload) or {
                "status": "captured",
                "blocks": len(payload.get("blocks", [])),
            },
            metadata_repository=repo,
        )

        if not success:
            raise RuntimeError("Structured ingestion failed: %s" % state.get("errors"))
        if state.get("warnings"):
            print("Warnings: %s" % state["warnings"])

        snapshot_id = state.get("metadata_snapshot_id")
        if not snapshot_id:
            raise RuntimeError("No metadata snapshot persisted.")

        tables = repo.list_tables(snapshot_id)
        columns = repo.list_columns(snapshot_id)
        blocks = emitted_payloads[0].get("blocks", []) if emitted_payloads else []

        print("Snowflake source: account=%s database=%s schema=%s" % (
            config.account_id, config.database, config.schema,
        ))
        print("Metadata snapshot ID: %s" % snapshot_id)
        print("Tables persisted: %d" % len(tables))
        print("Columns persisted: %d" % len(columns))
        print("SDK payload blocks captured: %d" % len(blocks))
        print("Live Snowflake -> Postgres structured ingestion completed successfully.")
        return 0
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
