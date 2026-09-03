#!/usr/bin/env python3
"""Validate a source registry entry and emit its adapter descriptor.

Zero dependency. Exits 0 when the entry yields status READY, 1 when it is
REJECTED. Every rejection prints its Core Rule ID.

Usage:  validate_registry_entry.py <entry.json>
"""
import json
import sys

# Capability sets are data, keyed by kind. Adding an adapter never edits logic
# below; adding a *kind* is the only reason to touch this table (REG02, REG03).
CAPABILITY_SETS = {
    "structured": ("write_probe", "statement_timeout", "row_cap", "schema_scope"),
    "unstructured": ("write_probe", "change_detection", "entitlement_capture",
                     "content_fetch", "incremental_sync"),
}

# Keys that describe how to reach an instance, not what the adapter can do.
CONNECTION_KEYS = (
    "host", "account", "url", "endpoint", "port", "database", "project_id",
    "credential_ref", "password", "token", "secret", "api_key", "private_key",
)

DESCRIPTOR_FIELDS = (
    "adapter", "kind", "dialect", "capabilities", "schema_version",
    "deprecated", "status", "violated_rule",
)


def reject(rule, adapter=None):
    return {
        "adapter": adapter, "kind": None, "dialect": None, "capabilities": None,
        "schema_version": None, "deprecated": None,
        "status": "REJECTED", "violated_rule": rule,
    }


def validate(entry):
    adapter = entry.get("adapter")

    # REG08 — every entry carries its schema version.
    if not entry.get("schema_version"):
        return reject("REG08", adapter)

    # REG07 — keys are immutable; supersession is a new key plus a deprecation.
    if entry.get("replaces") or entry.get("renamed_from"):
        return reject("REG07", adapter)

    # REG05 — the registry describes capability, never reachability.
    for key in CONNECTION_KEYS:
        if key in entry:
            return reject("REG05", adapter)

    # REG02 — kind discriminates the one registry; unknown kinds are refused.
    kind = entry.get("kind")
    if kind not in CAPABILITY_SETS:
        return reject("REG02", adapter)

    required = CAPABILITY_SETS[kind]
    caps = entry.get("capabilities")
    if not isinstance(caps, dict):
        return reject("REG03", adapter)

    # REG04 — an unrecognized key is a typo that would read as a silent False.
    for key in caps:
        if key not in required:
            return reject("REG04", adapter)

    # REG03 — the set must be exact, and every value an explicit boolean.
    for key in required:
        if key not in caps or not isinstance(caps[key], bool):
            return reject("REG03", adapter)

    # REG06 — dialect belongs to structured sources only.
    dialect = entry.get("dialect")
    if kind == "structured" and not dialect:
        return reject("REG06", adapter)
    if kind == "unstructured" and dialect is not None:
        return reject("REG06", adapter)

    return {
        "adapter": adapter,
        "kind": kind,
        "dialect": dialect if kind == "structured" else None,
        "capabilities": {k: caps[k] for k in required},
        "schema_version": entry["schema_version"],
        "deprecated": bool(entry.get("deprecated", False)),
        "status": "READY",
        "violated_rule": None,
    }


def main(argv):
    if len(argv) < 2:
        print("usage: validate_registry_entry.py <entry.json>")
        return 1

    with open(argv[1]) as fh:
        entry = json.load(fh)

    descriptor = validate(entry)

    # REG02 — one descriptor shape, whatever the kind or outcome.
    assert list(descriptor.keys()) == list(DESCRIPTOR_FIELDS), "descriptor shape drifted"

    print(json.dumps(descriptor, indent=2))
    if descriptor["status"] == "REJECTED":
        print("REJECTED by rule %s" % descriptor["violated_rule"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
