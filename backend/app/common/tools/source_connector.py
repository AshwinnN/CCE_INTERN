#!/usr/bin/env python3
"""Deterministic raw-content fetch for the ingestion workflow's fetch nodes.

Neither fetch_unstructured() nor fetch_structured() talks to a live provider
directly -- each takes an injected fetcher callable, the same fixture
convention agents/connector_agent/change_capture.py already uses for a live
driver read (object_lister / catalog_lister). That keeps this module
testable without live credentials; wiring a real fetcher is a caller
concern (see azure_blob_fetcher() below for the one real, env-driven
wiring this repo currently has a working client for).

snowflake_schema_fetcher() below is fetch_structured()'s equivalent real,
env-driven wiring -- backed by connectors.snowflake.SnowflakeConnector (a
real connection + a real write-probe, not a simulated one; see
structured_connector_architecture.md), closing the gap this module used to
document here.
"""
from typing import Callable, List, Optional


def fetch_unstructured(adapter: str, connection_handle: dict, object_id: str,
                        fetcher: Callable[[str, dict, str], bytes]) -> bytes:
    """Download raw bytes for object_id using the supplied fetcher.

    fetcher(adapter, connection_handle, object_id) -> bytes
    """
    if fetcher is None:
        raise RuntimeError(
            "fetch_unstructured: no fetcher configured for adapter %r" % adapter)
    return fetcher(adapter, connection_handle, object_id)


def fetch_structured(adapter: str, connection_handle: dict, schema_scope: List[str],
                      fetcher: Callable[[str, dict, List[str]], dict]) -> dict:
    """Fetch a schema card (schema + sample rows) using the supplied fetcher.

    fetcher(adapter, connection_handle, schema_scope) -> {"metadata": {...},
    "elements": [...]} -- already close to CanonicalDocument shape; see
    document_normalizer.normalize_to_canonical() for the final conversion.
    """
    if fetcher is None:
        raise RuntimeError(
            "fetch_structured: no fetcher configured for adapter %r" % adapter)
    return fetcher(adapter, connection_handle, schema_scope)


def azure_blob_fetcher(connection_string: str, container_name: str) -> Callable[[str, dict, str], bytes]:
    """Returns a fetch_unstructured-shaped fetcher bound to a real Azure Blob
    container, mirroring ingestion/azure_blob_source.py's download path.
    Only valid for adapter == "azure-blob"."""
    from azure.storage.blob import BlobServiceClient

    def _fetch(adapter: str, connection_handle: dict, object_id: str) -> bytes:
        if adapter != "azure-blob":
            raise ValueError(
                "azure_blob_fetcher only supports adapter='azure-blob', got %r" % adapter)
        service = BlobServiceClient.from_connection_string(connection_string)
        container = service.get_container_client(container_name)
        return container.get_blob_client(object_id).download_blob().readall()

    return _fetch


def snowflake_schema_fetcher(max_tables: Optional[int] = None) -> Callable[[str, dict, List[str]], dict]:
    """Returns a fetch_structured-shaped fetcher bound to a real, live
    connectors.snowflake.SnowflakeConnector, config assembled from
    CCE_SNOWFLAKE_* env vars. Opens a fresh connection per call (a fresh
    write-probe every time -- see connectors/snowflake/connector.py) and
    always closes it before returning, success or failure. Only valid for
    adapter == "snowflake"; `schema_scope[0]` overrides the env-default
    schema when the caller wants a specific one."""

    def _fetch(adapter: str, connection_handle: dict, schema_scope: List[str]) -> dict:
        if adapter != "snowflake":
            raise ValueError(
                "snowflake_schema_fetcher only supports adapter='snowflake', got %r" % adapter)
        from connectors.factory import ConnectorFactory
        from connectors.snowflake.config import build_config_from_env

        config = build_config_from_env(schema=schema_scope[0] if schema_scope else None)
        connector = ConnectorFactory.create(config)
        connector.connect()
        try:
            return connector.get_schema_card(config.schema, max_tables=max_tables)
        finally:
            connector.close()

    return _fetch
