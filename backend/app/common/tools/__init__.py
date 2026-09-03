#!/usr/bin/env python3
"""Deterministic tools used by agents/ingestion_workflow.py.

Every function here is a pure/deterministic step -- no ML, no judgment, no
external-service dependency baked in at import time. Anything that talks to
a live provider (source_connector's fetchers) takes the connection as an
injected callable, the same fixture convention change_capture.py's observers
already use for object_lister/catalog_lister -- so these tools stay testable
without live credentials, and swapping a real driver in is a caller concern,
not a change to this package.
"""
from .dlp_classifier import classify_text, redact_text, get_dlp_confidence_threshold
from .source_connector import fetch_unstructured, fetch_structured, azure_blob_fetcher, snowflake_schema_fetcher
from .document_normalizer import normalize_to_canonical
from .checkpoint_manager import IngestionCheckpointStore, get_ingestion_checkpoint_store
from .credential_loader import load_env_credential, load_snowflake_keypair_credential, CredentialResolutionError

__all__ = [
    "classify_text", "redact_text", "get_dlp_confidence_threshold",
    "fetch_unstructured", "fetch_structured", "azure_blob_fetcher", "snowflake_schema_fetcher",
    "normalize_to_canonical",
    "IngestionCheckpointStore", "get_ingestion_checkpoint_store",
    "load_env_credential", "load_snowflake_keypair_credential", "CredentialResolutionError",
]
