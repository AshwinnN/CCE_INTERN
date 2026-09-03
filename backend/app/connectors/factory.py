#!/usr/bin/env python3
"""Factory pattern: given a ConnectionConfig, return the right connector.

Callers depend on StructuredConnector (the interface), never on
SnowflakeConnector directly -- adding Postgres/BigQuery later is a new
connectors/<adapter>/ package plus one line in _connectors, never a change
to a caller.
"""
from typing import Type

from connectors.base.connector import StructuredConnector
from connectors.base.exceptions import UnsupportedAdapterError
from connectors.base.models import ConnectionConfig
from connectors.snowflake.connector import SnowflakeConnector


class ConnectorFactory:
    _connectors = {
        "snowflake": SnowflakeConnector,
        # "postgres": PostgresConnector,   # Phase 2
        # "bigquery": BigQueryConnector,   # Phase 3
    }

    @staticmethod
    def create(config: ConnectionConfig) -> StructuredConnector:
        connector_class = ConnectorFactory._connectors.get(config.adapter)
        if connector_class is None:
            raise UnsupportedAdapterError(
                "Unsupported adapter %r. Supported: %s"
                % (config.adapter, list(ConnectorFactory._connectors.keys())))
        return connector_class(config)

    @staticmethod
    def register(adapter: str, connector_class: Type[StructuredConnector]) -> None:
        """Register a new connector at runtime -- used by tests to inject a
        fake connector class without touching this module's defaults."""
        ConnectorFactory._connectors[adapter] = connector_class
