#!/usr/bin/env python3
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from common.tools.credential_loader import (  # noqa: E402
    CredentialResolutionError, load_env_credential, load_snowflake_keypair_credential,
)


class LoadEnvCredentialTests(unittest.TestCase):

    def tearDown(self):
        os.environ.pop("CCE_TEST_VAR", None)
        os.environ.pop("CCE_TEST_VAR_PASSPHRASE", None)

    def test_reads_the_named_env_var(self):
        os.environ["CCE_TEST_VAR"] = "shh-its-a-secret"
        self.assertEqual(load_env_credential("env://CCE_TEST_VAR"), "shh-its-a-secret")

    def test_missing_scheme_rejects(self):
        with self.assertRaises(CredentialResolutionError):
            load_env_credential("CCE_TEST_VAR")

    def test_unsupported_scheme_rejects(self):
        with self.assertRaises(CredentialResolutionError):
            load_env_credential("vault://cce/wh_prod")

    def test_unset_variable_rejects_rather_than_returning_empty_string(self):
        os.environ.pop("CCE_TEST_VAR", None)
        with self.assertRaises(CredentialResolutionError):
            load_env_credential("env://CCE_TEST_VAR")

    def test_empty_variable_rejects(self):
        os.environ["CCE_TEST_VAR"] = ""
        with self.assertRaises(CredentialResolutionError):
            load_env_credential("env://CCE_TEST_VAR")


class LoadSnowflakeKeypairCredentialTests(unittest.TestCase):

    def tearDown(self):
        os.environ.pop("CCE_TEST_VAR", None)
        os.environ.pop("CCE_TEST_VAR_PASSPHRASE", None)

    def test_returns_pem_and_none_passphrase_when_unset(self):
        os.environ["CCE_TEST_VAR"] = "-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----"
        result = load_snowflake_keypair_credential("env://CCE_TEST_VAR")
        self.assertEqual(result["private_key_pem"], os.environ["CCE_TEST_VAR"])
        self.assertIsNone(result["passphrase"])

    def test_reads_passphrase_from_the_var_name_plus_passphrase_convention(self):
        os.environ["CCE_TEST_VAR"] = "pem-content"
        os.environ["CCE_TEST_VAR_PASSPHRASE"] = "hunter2"
        result = load_snowflake_keypair_credential("env://CCE_TEST_VAR")
        self.assertEqual(result["passphrase"], "hunter2")

    def test_missing_key_variable_rejects(self):
        with self.assertRaises(CredentialResolutionError):
            load_snowflake_keypair_credential("env://CCE_TEST_VAR")


if __name__ == "__main__":
    unittest.main()
