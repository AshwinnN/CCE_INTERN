#!/usr/bin/env python3
"""Unit tests for repository/postgresql_metadata_repository.py -- no live
Postgres anywhere. `_cursor()` is monkeypatched to a fake context manager
around a fake cursor that just records (sql, params) and returns queued
fetchone/fetchall results, the same "inject the fixture, never the live
driver" convention tests/connectors/test_snowflake_connector.py already
uses for the Snowflake driver."""
import contextlib
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

import psycopg2.extras  # noqa: E402

from repository.base import SchemaSnapshot  # noqa: E402
from repository.postgresql_metadata_repository import (  # noqa: E402
    PostgreSQLMetadataRepository, _stable_uuid,
)


class FakeCursor:
    """Queue of return values, one per execute()+fetchone()/fetchall() pair."""

    def __init__(self, results):
        self._results = list(results)
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append((sql, params))

    def fetchone(self):
        return self._results.pop(0) if self._results else None

    def fetchall(self):
        return self._results.pop(0) if self._results else []


def make_repo(results):
    repo = PostgreSQLMetadataRepository.__new__(PostgreSQLMetadataRepository)
    cur = FakeCursor(results)

    @contextlib.contextmanager
    def fake_cursor():
        yield cur

    repo._cursor = fake_cursor
    return repo, cur


class StableUuidTests(unittest.TestCase):
    def test_same_inputs_produce_same_id(self):
        self.assertEqual(_stable_uuid("table", "schema1", "T1"), _stable_uuid("table", "schema1", "T1"))

    def test_different_inputs_produce_different_ids(self):
        self.assertNotEqual(_stable_uuid("table", "schema1", "T1"), _stable_uuid("table", "schema1", "T2"))
        self.assertNotEqual(_stable_uuid("table", "schema1", "T1"), _stable_uuid("table", "schema2", "T1"))


class EnsureHierarchyTests(unittest.TestCase):
    def test_ensure_source_returns_deterministic_id_and_upserts(self):
        expected_id = _stable_uuid("source", "snowflake", "acct1")
        repo, cur = make_repo([{"source_id": expected_id}])
        result = repo.ensure_source("snowflake", "acct1", "Acct One")
        self.assertEqual(result, expected_id)
        sql, params = cur.queries[0]
        self.assertIn("INSERT INTO cce_source", sql)
        self.assertIn("ON CONFLICT (adapter, account_id)", sql)
        self.assertEqual(params, (expected_id, "snowflake", "acct1", "Acct One"))

    def test_ensure_namespace(self):
        expected_id = _stable_uuid("namespace", "src1", "ANALYTICS_DB")
        repo, cur = make_repo([{"namespace_id": expected_id}])
        result = repo.ensure_namespace("src1", "ANALYTICS_DB", "catalog")
        self.assertEqual(result, expected_id)
        _, params = cur.queries[0]
        self.assertEqual(params, (expected_id, "src1", "ANALYTICS_DB", "catalog"))

    def test_ensure_schema(self):
        expected_id = _stable_uuid("schema", "ns1", "PUBLIC")
        repo, cur = make_repo([{"schema_id": expected_id}])
        result = repo.ensure_schema("ns1", "PUBLIC")
        self.assertEqual(result, expected_id)


class SnapshotTests(unittest.TestCase):
    def test_save_snapshot(self):
        repo, cur = make_repo([{"snapshot_id": "snap-1"}])
        snapshot = SchemaSnapshot(
            snapshot_id="snap-1", source_id="src1", schema_id="schema1",
            captured_at="2026-09-03T00:00:00Z", schema_hash="deadbeef", status="SUCCESS",
            table_count=2, column_count=5,
        )
        result = repo.save_snapshot(snapshot)
        self.assertEqual(result, "snap-1")
        _, params = cur.queries[0]
        self.assertEqual(params[0], "snap-1")
        self.assertEqual(params[5], "SUCCESS")

    def test_latest_snapshot_id_none_when_never_ingested(self):
        repo, _ = make_repo([None])
        self.assertIsNone(repo.latest_snapshot_id("schema1"))

    def test_latest_snapshot_id_returns_row(self):
        repo, _ = make_repo([{"snapshot_id": "snap-9"}])
        self.assertEqual(repo.latest_snapshot_id("schema1"), "snap-9")


class SaveTableColumnTests(unittest.TestCase):
    def test_save_table_id_is_deterministic_from_schema_and_name(self):
        expected_id = _stable_uuid("table", "schema1", "SALES")
        repo, cur = make_repo([{"table_id": expected_id}])
        result = repo.save_table({
            "snapshot_id": "snap1", "schema_id": "schema1", "table_name": "SALES",
            "table_type": "TABLE", "row_count": 100,
        })
        self.assertEqual(result, expected_id)
        _, params = cur.queries[0]
        self.assertEqual(params[0], expected_id)
        self.assertEqual(params[3], "SALES")
        self.assertIsInstance(params[8], psycopg2.extras.Json)

    def test_save_table_id_stable_across_snapshots(self):
        expected_id = _stable_uuid("table", "schema1", "SALES")
        repo, _ = make_repo([{"table_id": expected_id}, {"table_id": expected_id}])
        id_snap1 = repo.save_table({"snapshot_id": "snap1", "schema_id": "schema1", "table_name": "SALES"})
        id_snap2 = repo.save_table({"snapshot_id": "snap2", "schema_id": "schema1", "table_name": "SALES"})
        self.assertEqual(id_snap1, id_snap2)

    def test_save_column_canonical_type_and_detail_round_trip(self):
        table_id = "table-1"
        expected_id = _stable_uuid("column", table_id, "AMOUNT")
        repo, cur = make_repo([{"column_id": expected_id}])
        result = repo.save_column({
            "snapshot_id": "snap1", "table_id": table_id, "column_name": "AMOUNT",
            "ordinal_position": 2, "data_type": "NUMERIC",
            "type_detail": {"precision": 18, "scale": 2, "source_type": "NUMBER(18,2)"},
            "native_data_type": "NUMBER(18,2)", "numeric_precision": 18, "numeric_scale": 2,
        })
        self.assertEqual(result, expected_id)
        _, params = cur.queries[0]
        self.assertEqual(params[5], "NUMERIC")
        self.assertIsInstance(params[6], psycopg2.extras.Json)
        self.assertEqual(params[6].adapted, {"precision": 18, "scale": 2, "source_type": "NUMBER(18,2)"})
        self.assertEqual(params[7], "NUMBER(18,2)")


class ListAndQueryTests(unittest.TestCase):
    def test_list_tables_returns_rows_as_dicts(self):
        repo, _ = make_repo([[{"table_id": "t1", "table_name": "SALES"}]])
        self.assertEqual(repo.list_tables("snap1"), [{"table_id": "t1", "table_name": "SALES"}])

    def test_list_columns_filters_by_table_when_given(self):
        repo, cur = make_repo([[{"column_id": "c1"}]])
        repo.list_columns("snap1", table_id="t1")
        sql, params = cur.queries[0]
        self.assertIn("table_id = %s", sql)
        self.assertEqual(params, ("snap1", "t1"))

    def test_query_by_canonical_type_passes_filters(self):
        repo, cur = make_repo([[{"column_id": "c1", "data_type": "NUMERIC"}]])
        result = repo.query_by_canonical_type("NUMERIC", source_id="src1")
        self.assertEqual(result, [{"column_id": "c1", "data_type": "NUMERIC"}])
        _, params = cur.queries[0]
        self.assertEqual(params, {"data_type": "NUMERIC", "source_id": "src1"})


class RelationshipTests(unittest.TestCase):
    def test_save_relationship_inserts_relationship_and_mapping_rows(self):
        repo, cur = make_repo([])
        relationship_id = repo.save_relationship({
            "snapshot_id": "snap1", "source_table_id": "t1", "target_table_id": "t2",
            "relationship_type": "FOREIGN_KEY", "constraint_name": "fk_orders_customer",
            "column_mappings": [
                {"source_column_id": "c1", "target_column_id": "c2"},
                {"source_column_id": "c3", "target_column_id": "c4"},
            ],
        })
        self.assertEqual(len(cur.queries), 3)  # 1 relationship insert + 2 mapping inserts
        self.assertIn("INSERT INTO cce_relationship ", cur.queries[0][0])
        self.assertIn("INSERT INTO cce_relationship_column_mapping", cur.queries[1][0])
        self.assertEqual(cur.queries[1][1][2], 0)   # ordinal_position
        self.assertEqual(cur.queries[2][1][2], 1)
        self.assertTrue(relationship_id)


class DetectChangesTests(unittest.TestCase):
    def test_detect_changes_reports_added_and_removed_tables(self):
        repo, _ = make_repo([
            [{"table_name": "NEW_TABLE", "table_id": "t2"}],       # added
            [{"table_name": "OLD_TABLE", "table_id": "t1"}],       # removed
        ])
        changes = repo.detect_changes("snap1", "snap2")
        self.assertEqual(len(changes), 2)
        self.assertEqual(changes[0].change_type, "TABLE_ADDED")
        self.assertEqual(changes[0].table_name, "NEW_TABLE")
        self.assertEqual(changes[1].change_type, "TABLE_REMOVED")
        self.assertEqual(changes[1].table_name, "OLD_TABLE")


class CloseTests(unittest.TestCase):
    def test_close_is_idempotent(self):
        repo = PostgreSQLMetadataRepository.__new__(PostgreSQLMetadataRepository)

        class FakePool:
            def __init__(self):
                self.closed = False
                self.closeall_calls = 0

            def closeall(self):
                self.closeall_calls += 1
                self.closed = True

        repo._pool = FakePool()
        repo.close()
        repo.close()
        self.assertEqual(repo._pool.closeall_calls, 1)


if __name__ == "__main__":
    unittest.main()
