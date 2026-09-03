#!/usr/bin/env python3
"""MVP source-registry provider.

This module is the lookup boundary that turns `source_adapter` into a
registry descriptor. It performs no I/O and no credential handling; the
Connector Agent validates each returned descriptor before trusting it.

Capability keys are stable runtime contract names: write_probe,
statement_timeout, row_cap, schema_scope for structured sources; write_probe,
change_detection, entitlement_capture, content_fetch, incremental_sync for
unstructured sources.
"""
import copy

_STRUCTURED_CAPS = {
    "write_probe": True, "statement_timeout": True, "row_cap": True, "schema_scope": True,
}

_UNSTRUCTURED_CAPS_FULL = {
    "write_probe": True, "change_detection": True, "entitlement_capture": True,
    "content_fetch": True, "incremental_sync": True,
}

_UNSTRUCTURED_CAPS_SINGLE_OBJECT = {
    **_UNSTRUCTURED_CAPS_FULL, "incremental_sync": False,
}

_KNOWN_ADAPTERS = {
    # Structured sources.
    "snowflake":  {"adapter": "snowflake", "kind": "structured", "dialect": "snowflake",
                   "capabilities": _STRUCTURED_CAPS, "schema_version": "1.0",
                   "deprecated": False, "status": "READY", "violated_rule": None},
    "postgres":   {"adapter": "postgres", "kind": "structured", "dialect": "postgres",
                   "capabilities": _STRUCTURED_CAPS, "schema_version": "1.0",
                   "deprecated": False, "status": "READY", "violated_rule": None},
    "databricks": {"adapter": "databricks", "kind": "structured", "dialect": "databricks",
                   "capabilities": _STRUCTURED_CAPS, "schema_version": "1.0",
                   "deprecated": False, "status": "READY", "violated_rule": None},
    "bigquery":   {"adapter": "bigquery", "kind": "structured", "dialect": "bigquery",
                   "capabilities": _STRUCTURED_CAPS, "schema_version": "1.0",
                   "deprecated": False, "status": "READY", "violated_rule": None},

    # Unstructured sources.
    "google-drive": {"adapter": "google-drive", "kind": "unstructured", "dialect": None,
                      "capabilities": _UNSTRUCTURED_CAPS_FULL, "schema_version": "1.0",
                      "deprecated": False, "status": "READY", "violated_rule": None},
    "gmail":        {"adapter": "gmail", "kind": "unstructured", "dialect": None,
                      "capabilities": _UNSTRUCTURED_CAPS_FULL, "schema_version": "1.0",
                      "deprecated": False, "status": "READY", "violated_rule": None},
    "sharepoint":   {"adapter": "sharepoint", "kind": "unstructured", "dialect": None,
                      "capabilities": _UNSTRUCTURED_CAPS_FULL, "schema_version": "1.0",
                      "deprecated": False, "status": "READY", "violated_rule": None},
    "slack":        {"adapter": "slack", "kind": "unstructured", "dialect": None,
                      "capabilities": _UNSTRUCTURED_CAPS_FULL, "schema_version": "1.0",
                      "deprecated": False, "status": "READY", "violated_rule": None},
    "confluence":   {"adapter": "confluence", "kind": "unstructured", "dialect": None,
                      "capabilities": _UNSTRUCTURED_CAPS_FULL, "schema_version": "1.0",
                      "deprecated": False, "status": "READY", "violated_rule": None},
    "local-fs":     {"adapter": "local-fs", "kind": "unstructured", "dialect": None,
                      "capabilities": _UNSTRUCTURED_CAPS_SINGLE_OBJECT, "schema_version": "1.0",
                      "deprecated": False, "status": "READY", "violated_rule": None},
    "azure-blob":   {"adapter": "azure-blob", "kind": "unstructured", "dialect": None,
                      "capabilities": _UNSTRUCTURED_CAPS_FULL, "schema_version": "1.0",
                      "deprecated": False, "status": "READY", "violated_rule": None},
}


class AdapterRegistryProvider:
    """Interface a persistent registry service can implement."""

    def get(self, adapter_key):
        raise NotImplementedError


class StubAdapterRegistryProvider(AdapterRegistryProvider):
    """In-memory registry provider for local development and tests."""

    def get(self, adapter_key):
        entry = _KNOWN_ADAPTERS.get(adapter_key)
        # Return a copy: callers must never be able to mutate shared state
        # through the object they were handed.
        return copy.deepcopy(entry) if entry is not None else None
