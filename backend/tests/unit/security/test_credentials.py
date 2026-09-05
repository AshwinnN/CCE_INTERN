import os
import sys
import types
import unittest

from cce.security.credentials import (
    CredentialResolutionError,
    load_azure_kv_credential,
    load_snowflake_keypair_credential,
)


class AzureKeyVaultCredentialTests(unittest.TestCase):
    def setUp(self):
        self.original_modules = dict(sys.modules)

    def tearDown(self):
        sys.modules.clear()
        sys.modules.update(self.original_modules)
        os.environ.pop("CCE_TEST_VAR", None)
        os.environ.pop("CCE_TEST_VAR_PASSPHRASE", None)

    def _install_fake_azure_modules(self, value="secret-value", error=None):
        azure = types.ModuleType("azure")
        identity = types.ModuleType("azure.identity")
        keyvault = types.ModuleType("azure.keyvault")
        secrets = types.ModuleType("azure.keyvault.secrets")

        class DefaultAzureCredential:
            pass

        class SecretClient:
            def __init__(self, vault_url, credential):
                self.vault_url = vault_url
                self.credential = credential

            def get_secret(self, secret_name):
                if error:
                    raise error
                return types.SimpleNamespace(value=value, name=secret_name)

        identity.DefaultAzureCredential = DefaultAzureCredential
        secrets.SecretClient = SecretClient
        sys.modules["azure"] = azure
        sys.modules["azure.identity"] = identity
        sys.modules["azure.keyvault"] = keyvault
        sys.modules["azure.keyvault.secrets"] = secrets

    def test_load_azure_kv_credential_reads_secret(self):
        self._install_fake_azure_modules(value="db-password")
        self.assertEqual(
            load_azure_kv_credential("azure-kv://cce-vault/postgres-password"),
            "db-password",
        )

    def test_load_azure_kv_credential_wraps_failures(self):
        self._install_fake_azure_modules(error=RuntimeError("no auth"))
        with self.assertRaises(CredentialResolutionError):
            load_azure_kv_credential("azure-kv://cce-vault/postgres-password")

    def test_snowflake_keypair_reads_key_vault_passphrase_convention(self):
        values = {
            "snowflake-key": "pem-content",
            "snowflake-key-passphrase": "hunter2",
        }
        azure = types.ModuleType("azure")
        identity = types.ModuleType("azure.identity")
        keyvault = types.ModuleType("azure.keyvault")
        secrets = types.ModuleType("azure.keyvault.secrets")

        class DefaultAzureCredential:
            pass

        class SecretClient:
            def __init__(self, vault_url, credential):
                pass

            def get_secret(self, secret_name):
                return types.SimpleNamespace(value=values[secret_name])

        identity.DefaultAzureCredential = DefaultAzureCredential
        secrets.SecretClient = SecretClient
        sys.modules["azure"] = azure
        sys.modules["azure.identity"] = identity
        sys.modules["azure.keyvault"] = keyvault
        sys.modules["azure.keyvault.secrets"] = secrets

        result = load_snowflake_keypair_credential("azure-kv://vault/snowflake-key")
        self.assertEqual(result["private_key_pem"], "pem-content")
        self.assertEqual(result["passphrase"], "hunter2")
