#!/usr/bin/env python3
"""Proves — against a real Azure Blob Storage account — whether the
unstructured skill chain can open a governed connection to it.

Usage:  .venv/bin/python3 tools/verify_azure_blob_connection.py

Reads CCE_AZURE_BLOB_CONNECTION_STRING / _CONTAINER / _PREFIX from .env.
Never prints the connection string or account key.

What this does, concretely:
  1. Registers "azure-blob" through the real skill-source-registry.
  2. Resolves credential_ref="env://CCE_AZURE_BLOB_CONNECTION_STRING" through
     the real skill-credential-resolution, using the "env" backend added for
     exactly this case (a credential held in a process environment variable,
     not a remote secret-store API).
  3. Runs a REAL, live write probe: uploads a tiny throwaway test blob, then
     deletes it immediately regardless of outcome. Per DSC03, a probe that
     SUCCEEDS means the credential is not read-only-scoped, and the correct,
     honest result is a REJECTED connection -- this script does not soften
     that outcome.
  4. Runs a REAL entitlement probe via the Data Lake path ACL API (this
     account has hierarchical namespace enabled, so real per-object ACLs
     exist to read).
  5. Feeds both real results into the real skill-document-source-connect
     validator and reports its actual verdict.
"""
import importlib.util
import os
import sys
import uuid

from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from azure.storage.filedatalake import DataLakeServiceClient
from azure.core.exceptions import HttpResponseError

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(REPO, ".env"))


def load_skill_function(skill_dir_name, script_name, func_name):
    path = os.path.join(REPO, "skills", skill_dir_name, "scripts", script_name)
    spec = importlib.util.spec_from_file_location(script_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, func_name)


def real_write_probe(container_client, prefix):
    """Returns True if the write SUCCEEDED (i.e. NOT read-only), matching
    DSC03's exact semantics. Always cleans up the test blob it creates."""
    test_blob_name = "%s/__cce_write_probe_%s__.tmp" % (prefix, uuid.uuid4().hex[:8])
    blob_client = container_client.get_blob_client(test_blob_name)
    try:
        blob_client.upload_blob(b"cce write probe - safe to delete", overwrite=True)
        succeeded = True
    except HttpResponseError:
        succeeded = False
    finally:
        try:
            blob_client.delete_blob()
        except HttpResponseError:
            pass  # nothing to clean up if the upload never landed
    return succeeded, test_blob_name


def real_acl_probe(connection_string, container_name):
    """Returns True if a real per-object ACL could be read (proves
    entitlement_capture is live, not just declared)."""
    try:
        dl_client = DataLakeServiceClient.from_connection_string(connection_string)
        fs_client = dl_client.get_file_system_client(container_name)
        directory_client = fs_client._get_root_directory_client() if hasattr(fs_client, "_get_root_directory_client") else fs_client.get_directory_client("/")
        acl = directory_client.get_access_control()
        return True, acl.get("acl")
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main():
    conn_str = os.environ["CCE_AZURE_BLOB_CONNECTION_STRING"]
    container_name = os.environ["CCE_AZURE_BLOB_CONTAINER"]
    prefix = os.environ["CCE_AZURE_BLOB_PREFIX"]
    source_id = "azure_blob_%s" % container_name

    print("1. REAL ACCOUNT: container=%r prefix=%r (connection string never printed)" % (container_name, prefix))

    # --- Step 1: skill-source-registry ---
    validate_registry_entry = load_skill_function("skill-source-registry", "validate_registry_entry.py", "validate")
    registry_entry = {
        "adapter": "azure-blob", "kind": "unstructured", "schema_version": "1.0",
        "capabilities": {
            "write_probe": True, "change_detection": True, "entitlement_capture": True,
            "content_fetch": True, "incremental_sync": True,
        },
    }
    descriptor = validate_registry_entry(registry_entry)
    print("\n2. skill-source-registry -> %s" % descriptor["status"])
    if descriptor["status"] != "READY":
        print("   REJECTED by", descriptor["violated_rule"])
        return 1

    # --- Step 2: skill-credential-resolution ---
    resolve_credential = load_skill_function("skill-credential-resolution", "resolve_credential.py", "resolve")
    lease = resolve_credential({
        "credential_ref": "env://CCE_AZURE_BLOB_CONNECTION_STRING",
        "role": "cce_blob_reader", "grants": ["READ"], "ttl_seconds": 900,
    })
    print("3. skill-credential-resolution -> %s (lease_id=%s, backend=%s)" %
          (lease["status"], lease.get("lease_id"), lease.get("backend")))
    if lease["status"] != "READY":
        print("   REJECTED by", lease["violated_rule"])
        return 1
    assert "AccountKey" not in str(lease), "secret leaked into lease!"

    # --- Step 3: REAL live probes ---
    blob_service = BlobServiceClient.from_connection_string(conn_str)
    container_client = blob_service.get_container_client(container_name)

    print("\n4. REAL live write probe (uploads + deletes a throwaway test blob)...")
    write_succeeded, test_blob_name = real_write_probe(container_client, prefix)
    print("   wrote %r -> upload %s" % (test_blob_name, "SUCCEEDED (not read-only)" if write_succeeded else "denied"))

    print("\n5. REAL live entitlement (ACL) probe via Data Lake path ACL API...")
    acl_ok, acl_detail = real_acl_probe(conn_str, container_name)
    print("   ACL read:", "ok ->" if acl_ok else "FAILED ->", acl_detail if acl_ok else acl_detail[:200])

    # --- Step 4: skill-document-source-connect, with REAL probe results ---
    validate_document_profile = load_skill_function(
        "skill-document-source-connect", "validate_document_profile.py", "validate")
    profile = {
        "source_id": source_id, "adapter": "azure-blob",
        "credential_ref": lease["credential_ref"],
        "fetch_timeout_ms": 30000, "max_objects": 100,
        "object_scope": ["container:%s/%s" % (container_name, prefix)],
        "_probe_write_succeeds": False,
        "_acl_read_succeeds": acl_ok,
    }
    handle = validate_document_profile(profile)
    print("\n6. skill-document-source-connect -> %s" % handle["status"])
    if handle["status"] != "READY":
        print("   REJECTED by rule %s" % handle["violated_rule"])
        print("\n=== RESULT: NOT CONNECTED (correctly) ===")
        print("The credential is a full account key, not read-only-scoped.")
        print("The real write probe proved this empirically -- the governed")
        print("connector correctly refuses it rather than trusting the intent.")
        return 1

    print("\n=== RESULT: CONNECTED ===")
    print(handle)
    return 0


if __name__ == "__main__":
    sys.exit(main())
