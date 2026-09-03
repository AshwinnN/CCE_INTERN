#!/usr/bin/env python3
"""MVP STUB -- replace with a persistent Source Registry service/repository.

skill-source-registry validates a *submitted* registry entry; it has no
lookup-by-adapter-key function and no persistence. Nothing else in this repo
stores "here are the adapters we know about, keyed by name." The Connector
Agent needs exactly that to turn a request's `source_adapter` string into the
full candidate entry skill-source-registry.validate() can check.

This module is that lookup, and nothing else. It performs no I/O, no
credential handling, and no validation logic of its own -- every entry it
returns still has to pass skill-source-registry.validate() before the Agent
trusts it. Only adapters actually supported by an existing connect skill are
seeded here (matching skill-strucutred_source_connect's DEFAULT_REGISTRY and
skill-document-source-connect's REGISTRY); this is not a place to register a
new adapter that has no connect-skill support yet.

Capability keys match skill-source-registry's own CAPABILITY_SETS exactly
(write_probe, statement_timeout, row_cap, schema_scope for structured;
write_probe, change_detection, entitlement_capture, content_fetch,
incremental_sync for unstructured) -- not the illustrative "connect"/
"read_only" names used in early design prompts, per inspection of the real
script.
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
    # Structured -- matches skill-strucutred_source_connect's DEFAULT_REGISTRY.
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

    # Unstructured -- matches skill-document-source-connect's REGISTRY.
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
}


class AdapterRegistryProvider:
    """Interface a real persistent registry service should implement to
    replace this stub without any change to Agent orchestration code."""

    def get(self, adapter_key):
        raise NotImplementedError


class StubAdapterRegistryProvider(AdapterRegistryProvider):
    """MVP STUB -- replace with persistent Source Registry service/repository."""

    def get(self, adapter_key):
        entry = _KNOWN_ADAPTERS.get(adapter_key)
        # Return a copy: callers must never be able to mutate shared state
        # through the object they were handed.
        return copy.deepcopy(entry) if entry is not None else None
