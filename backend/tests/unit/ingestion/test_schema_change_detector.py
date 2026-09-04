#!/usr/bin/env python3
"""Unit tests for tools/schema_change_detector.py -- an in-memory fake
repository, no live database, verifying diff logic only."""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from cce.persistence.ports import MetadataRepository, SchemaChange  # noqa: E402
from cce.ingestion.change_detection.schema_change_detector import SchemaChangeDetector  # noqa: E402


class FakeMetadataRepository(MetadataRepository):
    """Minimal in-memory MetadataRepository -- only the methods
    SchemaChangeDetector actually calls are implemented."""

    def __init__(self, tables_by_snapshot, columns_by_snapshot, table_added=None, table_removed=None):
        self._tables = tables_by_snapshot
        self._columns = columns_by_snapshot
        self._table_added = table_added or []
        self._table_removed = table_removed or []

    def list_tables(self, snapshot_id):
        return self._tables.get(snapshot_id, [])

    def list_columns(self, snapshot_id, table_id=None):
        cols = self._columns.get(snapshot_id, [])
        if table_id:
            return [c for c in cols if c["table_id"] == table_id]
        return cols

    def detect_changes(self, snapshot_1, snapshot_2):
        changes = [SchemaChange("TABLE_ADDED", name) for name in self._table_added]
        changes += [SchemaChange("TABLE_REMOVED", name) for name in self._table_removed]
        return changes

    # unused by SchemaChangeDetector -- stubbed to satisfy the ABC
    def ensure_source(self, *a, **k): raise NotImplementedError
    def ensure_namespace(self, *a, **k): raise NotImplementedError
    def ensure_schema(self, *a, **k): raise NotImplementedError
    def save_snapshot(self, *a, **k): raise NotImplementedError
    def save_table(self, *a, **k): raise NotImplementedError
    def save_column(self, *a, **k): raise NotImplementedError
    def save_constraint(self, *a, **k): raise NotImplementedError
    def save_relationship(self, *a, **k): raise NotImplementedError
    def query_by_canonical_type(self, *a, **k): raise NotImplementedError
    def latest_snapshot_id(self, *a, **k): raise NotImplementedError
    def close(self): pass


class ColumnDiffTests(unittest.TestCase):
    def test_column_added(self):
        repo = FakeMetadataRepository(
            tables_by_snapshot={"s1": [{"table_id": "t1", "table_name": "SALES"}],
                                 "s2": [{"table_id": "t1", "table_name": "SALES"}]},
            columns_by_snapshot={
                "s1": [{"table_id": "t1", "column_name": "ID", "data_type": "INTEGER"}],
                "s2": [{"table_id": "t1", "column_name": "ID", "data_type": "INTEGER"},
                       {"table_id": "t1", "column_name": "AMOUNT", "data_type": "NUMERIC"}],
            },
        )
        changes = SchemaChangeDetector(repo).detect("s1", "s2")
        added = [c for c in changes if c.change_type == "COLUMN_ADDED"]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].table_name, "SALES")
        self.assertEqual(added[0].column_name, "AMOUNT")

    def test_column_removed(self):
        repo = FakeMetadataRepository(
            tables_by_snapshot={"s1": [{"table_id": "t1", "table_name": "SALES"}],
                                 "s2": [{"table_id": "t1", "table_name": "SALES"}]},
            columns_by_snapshot={
                "s1": [{"table_id": "t1", "column_name": "LEGACY_FLAG", "data_type": "BOOLEAN"}],
                "s2": [],
            },
        )
        changes = SchemaChangeDetector(repo).detect("s1", "s2")
        removed = [c for c in changes if c.change_type == "COLUMN_REMOVED"]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0].column_name, "LEGACY_FLAG")

    def test_column_type_changed(self):
        repo = FakeMetadataRepository(
            tables_by_snapshot={"s1": [{"table_id": "t1", "table_name": "SALES"}],
                                 "s2": [{"table_id": "t1", "table_name": "SALES"}]},
            columns_by_snapshot={
                "s1": [{"table_id": "t1", "column_name": "AMOUNT", "data_type": "INTEGER"}],
                "s2": [{"table_id": "t1", "column_name": "AMOUNT", "data_type": "NUMERIC"}],
            },
        )
        changes = SchemaChangeDetector(repo).detect("s1", "s2")
        type_changed = [c for c in changes if c.change_type == "COLUMN_TYPE_CHANGED"]
        self.assertEqual(len(type_changed), 1)
        self.assertEqual(type_changed[0].detail, {"before": "INTEGER", "after": "NUMERIC"})

    def test_unchanged_column_produces_no_change(self):
        repo = FakeMetadataRepository(
            tables_by_snapshot={"s1": [{"table_id": "t1", "table_name": "SALES"}],
                                 "s2": [{"table_id": "t1", "table_name": "SALES"}]},
            columns_by_snapshot={
                "s1": [{"table_id": "t1", "column_name": "ID", "data_type": "INTEGER"}],
                "s2": [{"table_id": "t1", "column_name": "ID", "data_type": "INTEGER"}],
            },
        )
        self.assertEqual(SchemaChangeDetector(repo).detect("s1", "s2"), [])

    def test_table_level_changes_delegated_to_repository(self):
        repo = FakeMetadataRepository(
            tables_by_snapshot={"s1": [], "s2": []}, columns_by_snapshot={"s1": [], "s2": []},
            table_added=["NEW_TABLE"], table_removed=["OLD_TABLE"],
        )
        changes = SchemaChangeDetector(repo).detect("s1", "s2")
        self.assertEqual({c.change_type for c in changes}, {"TABLE_ADDED", "TABLE_REMOVED"})


if __name__ == "__main__":
    unittest.main()
