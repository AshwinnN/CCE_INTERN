#!/usr/bin/env python3
"""Factory pattern: given a ConnectionConfig, return the right connector.

Callers depend on StructuredConnector (the interface), never on
SnowflakeConnector directly -- adding Postgres/BigQuery later is a new
connectors/<adapter>/ package plus one line in _connectors, never a change
to a caller.
"""
from typing import Type

from cce.connectors.base.connector import StructuredConnector
from cce.connectors.base.exceptions import UnsupportedAdapterError
from cce.connectors.base.models import ConnectionConfig
from cce.connectors.base.source import SourceConnector
from cce.connectors.structured.snowflake.connector import SnowflakeConnector


class ConnectorFactory:
    _connectors = {
        "snowflake": SnowflakeConnector,
        # "postgres": PostgresConnector,   # Phase 2
        # "bigquery": BigQueryConnector,   # Phase 3
    }
    _unstructured_connectors = {}

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

    @staticmethod
    def create_unstructured(adapter: str, **kwargs) -> SourceConnector:
        connector_class = ConnectorFactory._unstructured_connectors.get(adapter)
        if connector_class is None and adapter == "local-fs":
            from cce.connectors.unstructured.local_fs.connector import LocalFileSystemConnector
            connector_class = LocalFileSystemConnector
        if connector_class is None and adapter == "azure-blob":
            from cce.connectors.unstructured.azure_blob.connector import AzureBlobSource
            connector_class = AzureBlobSource
        if connector_class is None:
            raise UnsupportedAdapterError(
                "Unsupported unstructured adapter %r. Supported: %s"
                % (adapter, list(ConnectorFactory._unstructured_connectors.keys())))
        return connector_class(**kwargs)

    @staticmethod
    def register_unstructured(adapter: str, connector_class: Type[SourceConnector]) -> None:
        ConnectorFactory._unstructured_connectors[adapter] = connector_class
