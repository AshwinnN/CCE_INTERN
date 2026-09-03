#!/usr/bin/env python3
"""Deterministic, env-backend credential fetch for connectors/.

Mirrors skill-credential-resolution/references/backend-contract.md's
`fetch(ref, ttl_seconds) -> driver-native credential`: hands the secret
straight to the connection driver, out of band -- never through a lease,
never logged, never returned to a caller that only needed authorization
proof. skill-credential-resolution still owns the *authorization* question
(grants declared vs. actual, TTL ceilings); this module only answers "what
is the actual secret at this reference," for the one backend this repo has
real material for.

Only the "env" scheme is implemented -- the same backend
skills/skill-credential-resolution/scripts/resolve_credential.py's
BACKENDS table already declares for "a credential held in a local/process
environment variable (e.g. a .env-loaded value)". vault://, aws-sm://,
gcp-sm://, azure-kv:// are real secret-store integrations this repository
has no client library or endpoint for; adding one is a new function here,
never a reason to fake the others (same discipline as
common/tools/source_connector.py's fetch_structured() gap note).
"""
import os
from typing import Optional

SUPPORTED_SCHEMES = ("env",)


class CredentialResolutionError(Exception):
    pass


def _parse_ref(credential_ref: str):
    if not credential_ref or "://" not in credential_ref:
        raise CredentialResolutionError("credential_ref %r has no scheme" % credential_ref)
    scheme, path = credential_ref.split("://", 1)
    return scheme, path


def load_env_credential(credential_ref: str) -> str:
    """"env://VAR_NAME" -> os.environ["VAR_NAME"]. Raises
    CredentialResolutionError for an unsupported scheme or an unset/empty
    variable -- never returns a silent empty string as if it were a real
    (if blank) secret."""
    scheme, var_name = _parse_ref(credential_ref)
    if scheme not in SUPPORTED_SCHEMES:
        raise CredentialResolutionError(
            "unsupported credential backend %r (only %s implemented)" % (scheme, SUPPORTED_SCHEMES))
    value = os.environ.get(var_name)
    if not value:
        raise CredentialResolutionError("environment variable %r is unset" % var_name)
    return value


def load_snowflake_keypair_credential(credential_ref: str) -> dict:
    """Loads a Snowflake key-pair credential: the PEM private key at
    credential_ref, plus its passphrase (if any) at "<var_name>_PASSPHRASE"
    by convention -- same convention tools/verify_snowflake_connection.py
    already uses for a real key-pair connect.

    Returns {"private_key_pem": str, "passphrase": Optional[str]}.
    """
    _, var_name = _parse_ref(credential_ref)
    private_key_pem = load_env_credential(credential_ref)
    passphrase: Optional[str] = os.environ.get("%s_PASSPHRASE" % var_name) or None
    return {"private_key_pem": private_key_pem, "passphrase": passphrase}
