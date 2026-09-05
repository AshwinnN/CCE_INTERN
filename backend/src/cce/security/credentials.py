#!/usr/bin/env python3
"""Deterministic credential fetch for connectors/.

Mirrors skill-credential-resolution/references/backend-contract.md's
`fetch(ref, ttl_seconds) -> driver-native credential`: hands the secret
straight to the connection driver, out of band -- never through a lease,
never logged, never returned to a caller that only needed authorization
proof. skill-credential-resolution still owns the *authorization* question
(grants declared vs. actual, TTL ceilings); this module only answers "what
is the actual secret at this reference," for the one backend this repo has
real material for.

The "env" scheme remains for local dev/CI. The "azure-kv" scheme is for
Azure Key Vault references in production-like environments.
"""
import os
from typing import Optional
from urllib.parse import urlparse

SUPPORTED_SCHEMES = ("env", "azure-kv")


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
    if scheme != "env":
        raise CredentialResolutionError("credential_ref %r is not an env ref" % credential_ref)
    value = os.environ.get(var_name)
    if not value:
        raise CredentialResolutionError("environment variable %r is unset" % var_name)
    return value


def load_azure_kv_credential(credential_ref: str) -> str:
    """"azure-kv://vault-name/secret-name" -> Key Vault secret value.

    Authentication is intentionally delegated to DefaultAzureCredential so
    the deployment team can choose managed identity or service-principal
    environment variables without a code branch here.
    """
    parsed = urlparse(credential_ref)
    if parsed.scheme != "azure-kv" or not parsed.netloc or not parsed.path.strip("/"):
        raise CredentialResolutionError(
            "azure Key Vault credential refs must use azure-kv://<vault-name>/<secret-name>"
        )

    vault_name = parsed.netloc
    secret_name = parsed.path.strip("/")
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        client = SecretClient(
            vault_url=f"https://{vault_name}.vault.azure.net/",
            credential=DefaultAzureCredential(),
        )
        secret = client.get_secret(secret_name)
    except Exception as exc:
        raise CredentialResolutionError(
            "failed to resolve Azure Key Vault credential %r: %s"
            % (credential_ref, exc)
        ) from exc

    if not getattr(secret, "value", None):
        raise CredentialResolutionError(
            "Azure Key Vault secret %r is unset or empty" % secret_name
        )
    return secret.value


def _azure_kv_passphrase_ref(credential_ref: str) -> str:
    """Snowflake passphrase convention for Key Vault credentials.

    When the primary Snowflake private key ref is
    azure-kv://<vault>/<secret>, the optional passphrase is looked up at a
    second secret in the same vault named <secret>-passphrase.
    """
    parsed = urlparse(credential_ref)
    return "azure-kv://%s/%s-passphrase" % (parsed.netloc, parsed.path.strip("/"))


def _dispatch(credential_ref: str) -> str:
    scheme, _ = _parse_ref(credential_ref)
    if scheme == "env":
        return load_env_credential(credential_ref)
    if scheme == "azure-kv":
        return load_azure_kv_credential(credential_ref)
    raise CredentialResolutionError(
        "unsupported credential backend %r (supported: %s)"
        % (scheme, SUPPORTED_SCHEMES)
    )


def load_credential(credential_ref: str) -> str:
    return _dispatch(credential_ref)


def load_snowflake_keypair_credential(credential_ref: str) -> dict:
    """Loads a Snowflake key-pair credential: the PEM private key at
    credential_ref, plus its passphrase (if any) at "<var_name>_PASSPHRASE"
    by convention -- same convention tools/verify_snowflake_connection.py
    already uses for a real key-pair connect.

    Returns {"private_key_pem": str, "passphrase": Optional[str]}.
    """
    scheme, var_name = _parse_ref(credential_ref)
    private_key_pem = _dispatch(credential_ref)
    if scheme == "azure-kv":
        try:
            passphrase = _dispatch(_azure_kv_passphrase_ref(credential_ref))
        except CredentialResolutionError:
            passphrase = None
    else:
        passphrase = os.environ.get("%s_PASSPHRASE" % var_name) or None
    return {"private_key_pem": private_key_pem, "passphrase": passphrase}
