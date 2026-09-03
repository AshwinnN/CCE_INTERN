#!/usr/bin/env python3
"""Comprehensive schema-change detection between two snapshots of the same
schema. Layered on top of repository.base.MetadataRepository rather than
writing its own SQL: table diffing delegates to
MetadataRepository.detect_changes() (added/removed, by table_id -- see
repository/postgresql_metadata_repository.py's module docstring on why
table_id is stable across snapshots), and column diffing is done here in
Python against MetadataRepository.list_columns() -- keeps every SQL
statement in the repository layer, and this module's diff logic unit
-testable against a fake in-memory repository with no live database.

Constraint/relationship diffing is intentionally NOT implemented (MVP scope
deferral, same discipline as final_resolved_schema.md's Issue 6 profiling
deferral) -- add _detect_constraint_changes/_detect_relationship_changes the
same way _detect_column_changes is built here when that's actually needed.
"""
from typing import List

from repository.base import MetadataRepository, SchemaChange


class SchemaChangeDetector:
    def __init__(self, repository: MetadataRepository):
        self.repo = repository

    def detect(self, snapshot_1: str, snapshot_2: str) -> List[SchemaChange]:
        """All changes from snapshot_1 -> snapshot_2 (tables then columns)."""
        changes = list(self.repo.detect_changes(snapshot_1, snapshot_2))
        changes.extend(self._detect_column_changes(snapshot_1, snapshot_2))
        return changes

    def _detect_column_changes(self, snapshot_1: str, snapshot_2: str) -> List[SchemaChange]:
        cols_1 = {(c["table_id"], c["column_name"]): c for c in self.repo.list_columns(snapshot_1)}
        cols_2 = {(c["table_id"], c["column_name"]): c for c in self.repo.list_columns(snapshot_2)}
        tables_1 = {t["table_id"]: t["table_name"] for t in self.repo.list_tables(snapshot_1)}
        tables_2 = {t["table_id"]: t["table_name"] for t in self.repo.list_tables(snapshot_2)}

        changes: List[SchemaChange] = []
        for key, col in cols_2.items():
            table_id, column_name = key
            if key not in cols_1:
                changes.append(SchemaChange(
                    "COLUMN_ADDED", tables_2.get(table_id, str(table_id)), column_name,
                    detail={"data_type": col["data_type"]}))
                continue
            before, after = cols_1[key], col
            if before["data_type"] != after["data_type"]:
                changes.append(SchemaChange(
                    "COLUMN_TYPE_CHANGED", tables_2.get(table_id, str(table_id)), column_name,
                    detail={"before": before["data_type"], "after": after["data_type"]}))

        for key, col in cols_1.items():
            if key not in cols_2:
                table_id, column_name = key
                changes.append(SchemaChange(
                    "COLUMN_REMOVED", tables_1.get(table_id, str(table_id)), column_name,
                    detail={"data_type": col["data_type"]}))

        return changes
