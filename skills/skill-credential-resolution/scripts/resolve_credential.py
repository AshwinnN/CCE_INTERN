#!/usr/bin/env python3
"""Resolve a credential_ref to a least-privilege credential lease.

Zero dependency. Exits 0 when a lease is issued, 1 when the request is
REJECTED. Every rejection prints its Core Rule ID.

Usage:  resolve_credential.py <request.json>

The lease returned is opaque. Secret material is never read into it, never
printed and never serialized (CRD03) — a real backend hands the secret
straight to the driver out of band.
"""
import json
import sys

LEASE_FIELDS = (
    "lease_id", "credential_ref", "backend", "role", "grants",
    "grants_write", "ttl_seconds", "status", "violated_rule",
)

# Backends are data. Adding one is an entry here, never a branch below (CRD02).
BACKENDS = {
    "vault":    {"name": "hashicorp-vault",     "max_ttl_seconds": 3600},
    "aws-sm":   {"name": "aws-secrets-manager", "max_ttl_seconds": 3600},
    "gcp-sm":   {"name": "gcp-secret-manager",  "max_ttl_seconds": 3600},
    "azure-kv": {"name": "azure-key-vault",     "max_ttl_seconds": 3600},
    "secret":   {"name": "cce-internal-store",  "max_ttl_seconds": 900},
    # A credential held in a local/process environment variable (e.g. a
    # .env-loaded value), not a remote secret-store API. Short ceiling
    # because there is no revocation signal to rely on other than
    # re-resolving frequently.
    "env":      {"name": "process-environment", "max_ttl_seconds": 900},
}

# Any grant implying mutation. Superset-safe on purpose: a false rejection
# costs a config fix, a missed write grant costs a mutated warehouse.
WRITE_GRANTS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE",
    "GRANT", "REVOKE", "MERGE", "COPY", "WRITE", "MODIFY", "OWNERSHIP",
    "ALL", "ALL_PRIVILEGES", "SUPERUSER", "ADMIN",
}

# Fields that would carry a secret value rather than a reference to one.
INLINE_SECRET_KEYS = (
    "password", "secret", "token", "api_key", "private_key",
    "secret_value", "client_secret",
)


def reject(rule, ref=None):
    return {
        "lease_id": None, "credential_ref": ref, "backend": None, "role": None,
        "grants": None, "grants_write": None, "ttl_seconds": None,
        "status": "REJECTED", "violated_rule": rule,
    }


def resolve(request):
    ref = request.get("credential_ref")

    # CRD01 — a reference, never a value.
    for key in INLINE_SECRET_KEYS:
        if key in request:
            return reject("CRD01", ref)
    if not ref or "://" not in ref:
        return reject("CRD01", ref)

    # CRD03 — the caller may not ask for the secret to be returned.
    if request.get("return_secret") or request.get("include_secret"):
        return reject("CRD03", ref)

    # CRD02 — scheme must resolve in the backend registry.
    scheme = ref.split("://", 1)[0]
    backend = BACKENDS.get(scheme)
    if backend is None:
        return reject("CRD02", ref)

    # CRD04 — least privilege is verified here, not assumed downstream.
    grants = request.get("grants")
    if not isinstance(grants, list) or not grants:
        return reject("CRD04", ref)
    normalized = sorted({str(g).strip().upper() for g in grants})
    if any(g in WRITE_GRANTS for g in normalized):
        return reject("CRD04", ref)

    # CRD05 — bounded, positive, and within the backend's own ceiling.
    ttl = request.get("ttl_seconds")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
        return reject("CRD05", ref)
    if ttl > backend["max_ttl_seconds"]:
        return reject("CRD05", ref)

    role = request.get("role")
    if not role:
        return reject("CRD04", ref)

    # CRD06 — deterministic id from the reference's final segment.
    lease_id = "lse_%s" % ref.rsplit("/", 1)[-1]

    # CRD07 — one shape for every backend.
    return {
        "lease_id": lease_id,
        "credential_ref": ref,
        "backend": scheme,
        "role": role,
        "grants": normalized,
        "grants_write": False,
        "ttl_seconds": ttl,
        "status": "READY",
        "violated_rule": None,
    }


def main(argv):
    if len(argv) < 2:
        print("usage: resolve_credential.py <request.json>")
        return 1

    with open(argv[1]) as fh:
        request = json.load(fh)

    lease = resolve(request)
    assert list(lease.keys()) == list(LEASE_FIELDS), "lease shape drifted"

    # CRD03 — nothing resembling secret material may reach stdout.
    blob = json.dumps(lease).lower()
    for key in INLINE_SECRET_KEYS:
        assert key not in blob or key in str(lease.get("credential_ref", "")).lower(), \
            "secret-bearing key leaked into the lease"

    print(json.dumps(lease, indent=2))
    if lease["status"] == "REJECTED":
        print("REJECTED by rule %s" % lease["violated_rule"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
