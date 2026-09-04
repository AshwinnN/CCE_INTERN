"""Unstructured ingestion entry point."""

from cce.ingestion.orchestrator import run_ingestion


def ingest_unstructured(event, connection_handle, source_id, **kwargs):
    return run_ingestion(event, connection_handle, source_id, **kwargs)
