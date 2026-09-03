#!/usr/bin/env python3
"""Validate an unstructured source profile and emit its DocumentHandle.

Zero dependency. Exits 0 when READY, 1 when REJECTED. Every rejection prints
its Core Rule ID.

Usage:  validate_document_profile.py <profile.json>
"""
import json
import sys

# Adapter knowledge is data (DSC01). Mirrors the structured connect skill.
REGISTRY = {
    "google-drive":  {"write_probe": True,  "entitlement_capture": True},
    "gmail":         {"write_probe": True,  "entitlement_capture": True},
    "sharepoint":    {"write_probe": True,  "entitlement_capture": True},
    "slack":         {"write_probe": True,  "entitlement_capture": True},
    "confluence":    {"write_probe": True,  "entitlement_capture": True},
    # Local filesystem: write access provable via a live open-for-write
    # attempt; entitlements captured via POSIX owner/group/mode at stat time.
    "local-fs":      {"write_probe": True,  "entitlement_capture": True},
    # Azure Blob Storage with hierarchical namespace (ADLS Gen2) enabled:
    # write access provable via a live test-blob upload attempt; entitlement
    # capture via the Data Lake path ACL API (real per-object ACLs, unlike
    # flat/non-HNS blob storage which has no per-object ACL concept at all).
    "azure-blob":    {"write_probe": True,  "entitlement_capture": True},
    # Registered but unusable: cannot prove read-only.
    "legacy-ftp":    {"write_probe": False, "entitlement_capture": True},
    # Registered but unusable: no per-object ACLs to capture.
    "public-bucket": {"write_probe": True,  "entitlement_capture": False},
}

INLINE_CREDENTIAL_KEYS = ("password", "secret", "token", "api_key",
                          "private_key", "refresh_token")
FALLBACK_KEYS = ("fallback_source", "fallback_adapter", "on_failure_source")
CONTENT_KEYS = ("objects", "documents", "titles", "listing", "content")

HANDLE_FIELDS = (
    "handle_id", "source_id", "adapter", "read_only_verified",
    "entitlement_capture_verified", "fetch_timeout_ms", "max_objects",
    "object_scope", "status", "violated_rule",
)


def reject(rule, source_id=None):
    return {
        "handle_id": None, "source_id": source_id, "adapter": None,
        "read_only_verified": None, "entitlement_capture_verified": None,
        "fetch_timeout_ms": None, "max_objects": None, "object_scope": None,
        "status": "REJECTED", "violated_rule": rule,
    }


def validate(profile):
    source_id = profile.get("source_id")

    # DSC04 - a reference, never a value.
    for key in INLINE_CREDENTIAL_KEYS:
        if key in profile:
            return reject("DSC04", source_id)
    if not profile.get("credential_ref"):
        return reject("DSC04", source_id)

    # DSC07 - a silent fallback grounds an answer in the wrong corpus.
    for key in FALLBACK_KEYS:
        if key in profile:
            return reject("DSC07", source_id)

    # DSC01 - adapter resolves through the registry.
    entry = REGISTRY.get(profile.get("adapter"))
    if entry is None:
        return reject("DSC01", source_id)

    # DSC05 - an unbounded crawl is a denial of service against the source.
    timeout = profile.get("fetch_timeout_ms")
    max_objects = profile.get("max_objects")
    if timeout is None or max_objects is None:
        return reject("DSC05", source_id)

    # DSC10 - connect is not discovery.
    for key in CONTENT_KEYS:
        if key in profile:
            return reject("DSC10", source_id)

    # DSC03 - read-only proven, never trusted from a declared OAuth scope.
    if not entry["write_probe"]:
        return reject("DSC03", source_id)
    if bool(profile.get("_probe_write_succeeds", False)):
        return reject("DSC03", source_id)

    # DSC09 - documents carry per-object ACLs that warehouse tables do not.
    if not entry["entitlement_capture"]:
        return reject("DSC09", source_id)
    if profile.get("_acl_read_succeeds") is False:
        return reject("DSC09", source_id)

    return {
        "handle_id": "hnd_%s" % source_id,
        "source_id": source_id,
        "adapter": profile["adapter"],
        "read_only_verified": True,
        "entitlement_capture_verified": True,
        "fetch_timeout_ms": timeout,
        "max_objects": max_objects,
        "object_scope": profile.get("object_scope"),
        "status": "READY",
        "violated_rule": None,
    }


def main(argv):
    if len(argv) < 2:
        print("usage: validate_document_profile.py <profile.json>")
        return 1
    with open(argv[1]) as fh:
        profile = json.load(fh)
    handle = validate(profile)
    assert list(handle.keys()) == list(HANDLE_FIELDS), "handle shape drifted"
    print(json.dumps(handle, indent=2))
    if handle["status"] == "REJECTED":
        print("REJECTED by rule %s" % handle["violated_rule"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
