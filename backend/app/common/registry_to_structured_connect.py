#!/usr/bin/env python3
"""Orchestration-only reshape: skill-source-registry descriptor -> the
`registry` argument skill-strucutred_source_connect's validator expects.

This is plumbing, not a Skill. It does not re-implement any Core Rule from
either skill — it only translates an already-validated shape into the other
skill's declared input shape, and fails closed if the input isn't the shape
a valid, active, non-deprecated structured descriptor should be.

Zero dependency, deterministic, no I/O. Mirrors the house pattern used by
every skill script in this repo: a pure function, an explicit error/rule
code on rejection, and a thin CLI wrapper.

Usage: registry_to_structured_connect.py <descriptor.json>
"""
import json
import sys

# The only schema_versions this transform currently accepts. Extending this
# set is a data change here, never a reason to touch the validation logic
# below — same convention skill-source-registry itself uses for capability
# sets.
SUPPORTED_SCHEMA_VERSIONS = ("1.0",)

# skill-source-registry's real contract uses status READY|REJECTED, not the
# active/inactive wording in some illustrative examples. REGISTRY_INACTIVE
# is raised for anything other than READY, including REJECTED or missing.
ACTIVE_STATUS = "READY"

REQUIRED_STRUCTURED_CAPABILITIES = (
    "write_probe", "statement_timeout", "row_cap", "schema_scope",
)

OUTPUT_FIELDS = ("status", "error_code", "registry")


def _error(code):
    return {"status": "ERROR", "error_code": code, "registry": None}


def to_structured_connect_registry(registry_result: dict) -> dict:
    """Pure, deterministic transform. Never falls back to a default registry
    on failure — that decision belongs to the caller, and silently doing it
    here would hide exactly the failure this function exists to surface.

    Returns {"status": "OK", "error_code": None, "registry": {...}} or
    {"status": "ERROR", "error_code": "<CODE>", "registry": None}.
    """
    if not isinstance(registry_result, dict):
        return _error("REGISTRY_SCHEMA_UNSUPPORTED")

    # Check order follows the order specified for this transform: schema
    # version, status, deprecated, kind, violated_rule, then field presence.
    schema_version = registry_result.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        return _error("REGISTRY_SCHEMA_UNSUPPORTED")

    if registry_result.get("status") != ACTIVE_STATUS:
        return _error("REGISTRY_INACTIVE")

    if registry_result.get("deprecated") is not False:
        return _error("REGISTRY_DEPRECATED")

    if registry_result.get("kind") != "structured":
        return _error("REGISTRY_KIND_MISMATCH")

    if registry_result.get("violated_rule") is not None:
        return _error("REGISTRY_RULE_VIOLATION")

    adapter = registry_result.get("adapter")
    if not adapter:
        return _error("REGISTRY_ADAPTER_MISSING")

    dialect = registry_result.get("dialect")
    if not dialect:
        return _error("REGISTRY_DIALECT_MISSING")

    capabilities = registry_result.get("capabilities")
    if not isinstance(capabilities, dict):
        return _error("REGISTRY_CAPABILITIES_INVALID")
    for key in REQUIRED_STRUCTURED_CAPABILITIES:
        if key not in capabilities or not isinstance(capabilities[key], bool):
            return _error("REGISTRY_CAPABILITIES_INVALID")

    return {
        "status": "OK",
        "error_code": None,
        "registry": {
            adapter: {
                "dialect": dialect,
                "supports": {k: capabilities[k] for k in REQUIRED_STRUCTURED_CAPABILITIES},
            }
        },
    }


def main(argv):
    if len(argv) < 2:
        print("usage: registry_to_structured_connect.py <descriptor.json>")
        return 1
    with open(argv[1]) as fh:
        descriptor = json.load(fh)
    result = to_structured_connect_registry(descriptor)
    assert list(result.keys()) == list(OUTPUT_FIELDS), "result shape drifted"
    print(json.dumps(result, indent=2))
    if result["status"] == "ERROR":
        print("REJECTED by %s" % result["error_code"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
