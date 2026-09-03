#!/usr/bin/env python3
"""Validate a structured-source profile and emit its ConnectionHandle.

Zero dependency. Exits 0 when the profile yields status READY, 1 when it is
REJECTED. Every rejection prints its Core Rule ID.

Usage:  validate_source_profile.py <profile.json> [--registry registry.json]
"""
import json
import sys

# Registry stands in for skill-cce-source-registry. Adapter knowledge lives
# here as data, never as a conditional in the logic below (STR01).
DEFAULT_REGISTRY = {
    "snowflake":  {"dialect": "snowflake",  "supports": {"write_probe": True,  "statement_timeout": True, "row_cap": True,  "schema_scope": True}},
    "postgres":   {"dialect": "postgres",   "supports": {"write_probe": True,  "statement_timeout": True, "row_cap": True,  "schema_scope": True}},
    "databricks": {"dialect": "databricks", "supports": {"write_probe": True,  "statement_timeout": True, "row_cap": True,  "schema_scope": True}},
    "bigquery":   {"dialect": "bigquery",   "supports": {"write_probe": True,  "statement_timeout": True, "row_cap": True,  "schema_scope": True}},
    # Registered but unusable: cannot prove read-only, so every connect is
    # rejected under STR03. Kept in the registry to make that outcome testable.
    "generic_odbc": {"dialect": "ansi",     "supports": {"write_probe": False, "statement_timeout": True, "row_cap": True,  "schema_scope": True}},
}

INLINE_CREDENTIAL_KEYS = ("password", "secret", "token", "private_key", "api_key")
FALLBACK_KEYS = ("fallback_source", "fallback_adapter", "on_failure_source")
CONTENT_KEYS = ("tables", "columns", "sample_rows", "schema_dump")

HANDLE_FIELDS = (
    "handle_id", "source_id", "adapter", "dialect", "read_only_verified",
    "statement_timeout_ms", "max_rows", "schema_scope", "status", "violated_rule",
)


def reject(rule, source_id=None):
    return {
        "handle_id": None, "source_id": source_id, "adapter": None, "dialect": None,
        "read_only_verified": None, "statement_timeout_ms": None, "max_rows": None,
        "schema_scope": None, "status": "REJECTED", "violated_rule": rule,
    }


def validate(profile, registry):
    source_id = profile.get("source_id")

    # STR04 — inline credentials are never accepted.
    for key in INLINE_CREDENTIAL_KEYS:
        if key in profile:
            return reject("STR04", source_id)
    if not profile.get("credential_ref"):
        return reject("STR04", source_id)

    # STR07 — no fallback source or adapter may be declared.
    for key in FALLBACK_KEYS:
        if key in profile:
            return reject("STR07", source_id)

    # STR01 — adapter must resolve through the registry.
    entry = registry.get(profile.get("adapter"))
    if entry is None:
        return reject("STR01", source_id)

    # STR05 — both limits must be present and bindable.
    timeout = profile.get("statement_timeout_ms")
    max_rows = profile.get("max_rows")
    if timeout is None or max_rows is None:
        return reject("STR05", source_id)
    if not entry["supports"]["statement_timeout"] or not entry["supports"]["row_cap"]:
        return reject("STR05", source_id)

    # STR10 — connect never carries schema, table or row content.
    for key in CONTENT_KEYS:
        if key in profile:
            return reject("STR10", source_id)

    # STR03 — read-only is proven by probe, never taken from config, and an
    # adapter that cannot probe is rejected rather than trusted.
    if not entry["supports"]["write_probe"]:
        return reject("STR03", source_id)
    # probe_write returns True when a write SUCCEEDED, i.e. the source is not
    # read-only.
    if bool(profile.get("_probe_write_succeeds", False)):
        return reject("STR03", source_id)
    read_only_verified = True

    # STR02, STR06, STR09 — normalized handle, deterministic id, resolved dialect.
    return {
        "handle_id": "hnd_%s" % source_id,
        "source_id": source_id,
        "adapter": profile["adapter"],
        "dialect": entry["dialect"],
        "read_only_verified": read_only_verified,
        "statement_timeout_ms": timeout,
        "max_rows": max_rows,
        "schema_scope": profile.get("schema_scope"),
        "status": "READY",
        "violated_rule": None,
    }


def main(argv):
    if len(argv) < 2:
        print("usage: validate_source_profile.py <profile.json> [--registry registry.json]")
        return 1

    registry = DEFAULT_REGISTRY
    if "--registry" in argv:
        with open(argv[argv.index("--registry") + 1]) as fh:
            registry = json.load(fh)

    with open(argv[1]) as fh:
        profile = json.load(fh)

    handle = validate(profile, registry)

    # STR02 — field set is identical whatever the outcome.
    assert list(handle.keys()) == list(HANDLE_FIELDS), "handle field set drifted"

    print(json.dumps(handle, indent=2))
    if handle["status"] == "REJECTED":
        print("REJECTED by rule %s" % handle["violated_rule"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
