#!/usr/bin/env python3
"""Abstract interface for the CCE structured-metadata repository. See
schema/*.sql for the backing tables and
CCE_STRUCTURED_METADATA_IMPLEMENTATION_PROMPT.md for the design this
follows -- adapted to this repo's real conventions (see
repository/postgresql_metadata_repository.py's module docstring for what
changed from the source prompt's sketch, and why).

Synchronous by design, not `async def` as the source prompt sketches --
matches connectors/base/connector.py's own documented choice: this repo has
no asyncio runtime anywhere else, and this repository's sole caller
(agents/ingestion_workflow.py's persist_structured_metadata_node) runs
inside a plain LangGraph node, not an event loop.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SchemaSnapshot:
    snapshot_id: str
    source_id: str
    schema_id: Optional[str]
    captured_at: Any             # datetime; repo stores as TIMESTAMPTZ
    schema_hash: str
    status: str                  # 'SUCCESS' | 'PARTIAL' | 'FAILED'
    table_count: Optional[int] = None
    column_count: Optional[int] = None
    error_detail: Optional[str] = None


@dataclass
class SchemaChange:
    change_type: str             # 'TABLE_ADDED' | 'TABLE_REMOVED' | 'COLUMN_ADDED' |
                                  # 'COLUMN_REMOVED' | 'COLUMN_TYPE_CHANGED'
    table_name: str
    column_name: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)


class MetadataRepository(ABC):
    """One structured-metadata store, keyed by (source, namespace, schema,
    snapshot). Every save_* method is idempotent for a given (id,
    snapshot_id) pair -- a retried call upserts, it never duplicates a row
    or mutates another snapshot's row (see schema/03_metadata.sql's module
    comment on deterministic ids)."""

    @abstractmethod
    def ensure_source(self, adapter: str, account_id: str,
                       display_name: Optional[str] = None) -> str:
        """Get-or-create a cce_source row. Returns source_id."""

    @abstractmethod
    def ensure_namespace(self, source_id: str, namespace_name: str, namespace_type: str) -> str:
        """Get-or-create a cce_namespace row. namespace_type: 'catalog' | 'database'.
        Returns namespace_id."""

    @abstractmethod
    def ensure_schema(self, namespace_id: str, schema_name: str) -> str:
        """Get-or-create a cce_schema row. Returns schema_id."""

    @abstractmethod
    def save_snapshot(self, snapshot: SchemaSnapshot) -> str:
        """Insert a new cce_schema_snapshot row. Returns snapshot_id."""

    @abstractmethod
    def save_table(self, table_record: Dict[str, Any]) -> str:
        """Upsert a cce_table row. Requires 'snapshot_id', 'schema_id',
        'table_name'. Returns table_id (deterministic, derived from
        schema_id + table_name -- stable across snapshots)."""

    @abstractmethod
    def save_column(self, column_record: Dict[str, Any]) -> str:
        """Upsert a cce_column row. Requires 'snapshot_id', 'table_id',
        'column_name', 'data_type' (CANONICAL, see connectors/canonical_types.py),
        'native_data_type'. Returns column_id (deterministic, derived from
        table_id + column_name)."""

    @abstractmethod
    def save_constraint(self, constraint_record: Dict[str, Any]) -> str:
        """Upsert a cce_constraint row. Returns constraint_id."""

    @abstractmethod
    def save_relationship(self, relationship_record: Dict[str, Any]) -> str:
        """Upsert a cce_relationship row plus its
        cce_relationship_column_mapping rows
        (relationship_record['column_mappings']: ordered list of
        {'source_column_id', 'target_column_id'}). Returns relationship_id."""

    @abstractmethod
    def list_tables(self, snapshot_id: str) -> List[Dict[str, Any]]:
        """All cce_table rows for one snapshot."""

    @abstractmethod
    def list_columns(self, snapshot_id: str, table_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """All cce_column rows for one snapshot, optionally filtered to one table_id."""

    @abstractmethod
    def query_by_canonical_type(self, data_type: str,
                                 source_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Columns matching a canonical data_type, from each schema's latest
        snapshot -- the cross-vendor "unified query"
        canonical_types_implementation_diagram.md's Step 5 describes."""

    @abstractmethod
    def latest_snapshot_id(self, schema_id: str) -> Optional[str]:
        """Most recent SUCCESS/PARTIAL snapshot_id for a schema, or None if
        it has never been successfully ingested."""

    @abstractmethod
    def detect_changes(self, snapshot_1: str, snapshot_2: str) -> List[SchemaChange]:
        """Table/column changes between two snapshots of the SAME schema.
        Thin pass-through most callers should prefer
        tools/schema_change_detector.SchemaChangeDetector over calling
        directly -- that module also diffs constraints/relationships."""

    @abstractmethod
    def close(self) -> None:
        """Release connections. Idempotent."""
