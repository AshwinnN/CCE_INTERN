#!/usr/bin/env python3
"""Live integration test: connects to a real Postgres instance (docker
compose up -d postgres && bash schema/init_db.sh) through
repository.PostgreSQLMetadataRepository -- proves the schema/*.sql DDL and
the repository's SQL actually work against a live database, the same way
tests/connectors/test_snowflake_integration.py proves the Snowflake
connector live. Skips (does not fail) when CCE_METADATA_REPOSITORY_ENABLED
isn't "true", matching that test's convention.

Run:  docker compose up -d postgres && bash schema/init_db.sh && \
      CCE_METADATA_REPOSITORY_ENABLED=true CCE_METADATA_DATABASE_URL=postgresql://cce_admin:cce_password@localhost:5432/cce_metadata \
      .venv/bin/python3 tests/repository/test_postgresql_integration.py
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(REPO, ".env"))

from connectors.canonical_types import canonicalize_type  # noqa: E402
from repository.base import SchemaSnapshot  # noqa: E402
from repository.postgresql_metadata_repository import PostgreSQLMetadataRepository  # noqa: E402


@unittest.skipUnless(
    os.environ.get("CCE_METADATA_REPOSITORY_ENABLED", "false").lower() == "true",
    "CCE_METADATA_REPOSITORY_ENABLED is not 'true' -- skipping live Postgres test",
)
class PostgreSQLMetadataRepositoryLiveIntegrationTests(unittest.TestCase):

    def setUp(self):
        dsn = os.environ["CCE_METADATA_DATABASE_URL"]
        self.repo = PostgreSQLMetadataRepository(dsn)

    def tearDown(self):
        self.repo.close()

    def test_full_snapshot_round_trip_and_idempotent_retry(self):
        import datetime
        import uuid

        source_id = self.repo.ensure_source("snowflake", "test_account", "Test Account")
        namespace_id = self.repo.ensure_namespace(source_id, "ANALYTICS_DB", "catalog")
        schema_id = self.repo.ensure_schema(namespace_id, "PUBLIC")

        snapshot_id = str(uuid.uuid4())
        self.repo.save_snapshot(SchemaSnapshot(
            snapshot_id=snapshot_id, source_id=source_id, schema_id=schema_id,
            captured_at=datetime.datetime.now(datetime.timezone.utc),
            schema_hash="test-hash", status="SUCCESS", table_count=1, column_count=1,
        ))

        table_id = self.repo.save_table({
            "snapshot_id": snapshot_id, "schema_id": schema_id,
            "table_name": "SALES", "row_count": 10,
        })
        data_type, type_detail = canonicalize_type("NUMBER(18,2)", "snowflake")
        self.repo.save_column({
            "snapshot_id": snapshot_id, "table_id": table_id, "column_name": "AMOUNT",
            "ordinal_position": 1, "data_type": data_type, "type_detail": type_detail,
            "native_data_type": "NUMBER(18,2)",
        })

        columns = self.repo.list_columns(snapshot_id)
        self.assertEqual(len(columns), 1)
        self.assertEqual(columns[0]["data_type"], "NUMERIC")

        matches = self.repo.query_by_canonical_type("NUMERIC", source_id=source_id)
        self.assertTrue(any(m["column_id"] == columns[0]["column_id"] for m in matches))

        # retry: same snapshot_id, same table/column identity -> no duplicate rows
        retried_table_id = self.repo.save_table({
            "snapshot_id": snapshot_id, "schema_id": schema_id, "table_name": "SALES",
        })
        self.assertEqual(retried_table_id, table_id)
        self.assertEqual(len(self.repo.list_tables(snapshot_id)), 1)


if __name__ == "__main__":
    unittest.main()
