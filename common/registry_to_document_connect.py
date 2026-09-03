#!/usr/bin/env python3
"""Orchestration-only validation for the unstructured lane's registry entry.

Unlike skill-strucutred_source_connect, skill-document-source-connect's
script (validate_document_profile.py) takes NO external registry parameter
at all -- its adapter table is fully internal, with no `--registry`-style
override point. So there is no DTO shape to reshape *into*; modifying that
skill's wrapper to accept one would violate "do not modify a Skill wrapper
merely to accept another Skill's DTO shape."

What this module does instead: the same fail-closed validation
registry_to_structured_connect.py performs (schema version, status,
deprecated, violated_rule, adapter, capabilities), scoped to kind ==
"unstructured", so the Agent can reject an invalid/inactive/deprecated
unstructured registry entry *before* calling the connect skill -- exactly
the same gate the structured lane gets, just without a reshape step at the
end, because none is needed.

Zero dependency, deterministic, no I/O.
"""
import json
import sys

SUPPORTED_SCHEMA_VERSIONS = ("1.0",)
ACTIVE_STATUS = "READY"

REQUIRED_UNSTRUCTURED_CAPABILITIES = (
    "write_probe", "change_detection", "entitlement_capture",
    "content_fetch", "incremental_sync",
)

OUTPUT_FIELDS = ("status", "error_code", "capabilities")


def _error(code):
    return {"status": "ERROR", "error_code": code, "capabilities": None}


def validate_document_connect_registry(registry_result: dict) -> dict:
    """Pure, deterministic validation. Never falls back to any default on
    failure -- returns capabilities: None and an explicit error_code.

    Returns {"status": "OK", "error_code": None, "capabilities": {...}} or
    {"status": "ERROR", "error_code": "<CODE>", "capabilities": None}.
    """
    if not isinstance(registry_result, dict):
        return _error("REGISTRY_SCHEMA_UNSUPPORTED")

    if registry_result.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        return _error("REGISTRY_SCHEMA_UNSUPPORTED")

    if registry_result.get("status") != ACTIVE_STATUS:
        return _error("REGISTRY_INACTIVE")

    if registry_result.get("deprecated") is not False:
        return _error("REGISTRY_DEPRECATED")

    if registry_result.get("kind") != "unstructured":
        return _error("REGISTRY_KIND_MISMATCH")

    if registry_result.get("violated_rule") is not None:
        return _error("REGISTRY_RULE_VIOLATION")

    if not registry_result.get("adapter"):
        return _error("REGISTRY_ADAPTER_MISSING")

    capabilities = registry_result.get("capabilities")
    if not isinstance(capabilities, dict):
        return _error("REGISTRY_CAPABILITIES_INVALID")
    for key in REQUIRED_UNSTRUCTURED_CAPABILITIES:
        if key not in capabilities or not isinstance(capabilities[key], bool):
            return _error("REGISTRY_CAPABILITIES_INVALID")

    return {
        "status": "OK",
        "error_code": None,
        "capabilities": {k: capabilities[k] for k in REQUIRED_UNSTRUCTURED_CAPABILITIES},
    }


def main(argv):
    if len(argv) < 2:
        print("usage: registry_to_document_connect.py <descriptor.json>")
        return 1
    with open(argv[1]) as fh:
        descriptor = json.load(fh)
    result = validate_document_connect_registry(descriptor)
    assert list(result.keys()) == list(OUTPUT_FIELDS), "result shape drifted"
    print(json.dumps(result, indent=2))
    if result["status"] == "ERROR":
        print("REJECTED by %s" % result["error_code"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
