#!/usr/bin/env python3
"""Abstract interface every structured source must implement.

No vendor name appears here, and no method may be added that only makes
sense for one adapter -- if it's Snowflake-only, it belongs on
SnowflakeConnector, not here (see structured_connector_quick_reference.md's
"Abstract vs Concrete" table).

Synchronous by design: every other I/O-performing module in this repo
(ingestion/parsers, ingestion/azure_blob_source, agents/connector_agent/*)
is synchronous, and this package's sole caller
(agents/ingestion_workflow.py's fetch_structured node) runs inside a plain
LangGraph node, not an event loop. The source design docs specified `async
def`; that choice bought nothing here (no concurrent connections are
opened) and would have forced an asyncio runtime onto call sites that don't
have one -- deferred, not implemented, if a real concurrency need appears.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class StructuredConnector(ABC):
    """
    Pure contract: what can you do with any structured database?
    connectors/factory.py hands the caller this type; the caller never
    imports a concrete adapter directly.
    """

    @abstractmethod
    def connect(self) -> "StructuredConnection":  # noqa: F821
        """Establish a connection and, when enabled, prove it is read-only
        via a live write probe before returning.

        Returns: StructuredConnection (with read_only_verified indicating proof)
        Raises: cce.connectors.base.exceptions.StructuredConnectorException
        (ConnectionFailedError if the driver-level connect fails,
        WriteAccessDetectedError if the probe's write succeeded)
        """

    @abstractmethod
    def get_schema_card(self, schema: str, max_tables: Optional[int] = None) -> Dict[str, Any]:
        """
        Fetch schema metadata: tables, columns, types, nullability, row
        count, and one sample row per table -- identical shape for every
        adapter:
            {"schema": str,
             "tables": [{"name": str,
                         "columns": [{"name": str, "type": str, "nullable": bool}, ...],
                         "row_count": Optional[int],
                         "sample_row": Optional[dict]}, ...]}
        """

    @abstractmethod
    def execute_query(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Execute a read-only (SELECT) query and return rows as dicts."""

    @abstractmethod
    def close(self) -> None:
        """Close the connection and release resources. Idempotent."""
