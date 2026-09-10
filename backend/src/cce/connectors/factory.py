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
    @staticmethod
    def create_source(source_type, config, credential_ref, source_id, *, draft=False):
        """Build from the production catalog without resolving secrets during validation."""
        from cce.sources.catalog import source_type_definition
        definition = source_type_definition(source_type)
        parsed = definition.validate_config(config, draft=draft)
        if not credential_ref or not credential_ref.strip():
            raise ValueError("credential_ref is required")
        if source_type in {"postgresql", "sql_server", "mysql"}:
            from cce.connectors.structured.relational import RelationalConnector
            return RelationalConnector(source_type, parsed, credential_ref)
        if source_type == "snowflake":
            selection = parsed.schema_selection
            # Temporary-table creation is not proof of write access in Snowflake.
            # Keep the connection unverified; guarded SELECT execution is allowed.
            return SnowflakeConnector(ConnectionConfig(adapter="snowflake", account_id=parsed.account_id,
                user=parsed.user, credential_ref=credential_ref, database=parsed.database,
                schema=selection.schemas[0] if selection and selection.schemas else "",
                role=parsed.role, warehouse=parsed.warehouse, max_rows=parsed.max_rows,
                login_timeout_s=parsed.login_timeout_s, network_timeout_s=parsed.network_timeout_s,
                authentication=parsed.authentication, write_probe_enabled=False))
        if source_type == "google_drive":
            from cce.connectors.unstructured.google_drive.connector import GoogleDriveConnector
            return GoogleDriveConnector(parsed, credential_ref, source_id)
        from cce.connectors.unstructured.azure_blob.connector import AzureBlobSource
        from cce.security.credentials import load_credential
        secret = load_credential(credential_ref)
        if parsed.authentication == "connection_string":
            return AzureBlobSource(secret, parsed.container, source_id, prefix=parsed.prefix, recursive=parsed.recursive)
        from azure.identity import ClientSecretCredential
        from azure.storage.blob import BlobServiceClient
        credential = ClientSecretCredential(parsed.tenant_id, parsed.client_id, secret)
        client = BlobServiceClient(parsed.account_url, credential=credential)
        return AzureBlobSource("", parsed.container, source_id, service_client=client,
                               prefix=parsed.prefix, recursive=parsed.recursive, credential=credential)

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
