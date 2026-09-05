import os
import unittest
from unittest import mock

from cce.config import settings


class SettingsDatabaseUrlTests(unittest.TestCase):
    def tearDown(self):
        for name in (
            "CCE_ENVIRONMENT",
            "CCE_ENV",
            "CCE_CONTROL_DATABASE_URL",
            "CCE_METADATA_DATABASE_URL",
            "CCE_CONTROL_DATABASE_CREDENTIAL_REF",
            "POSTGRES_USER",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "POSTGRES_DB",
        ):
            os.environ.pop(name, None)

    def test_local_env_without_config_uses_documented_default(self):
        os.environ["CCE_ENVIRONMENT"] = "local"
        self.assertEqual(
            settings._build_database_url(),
            "postgresql://cce_admin:cce_password@localhost:5434/cce_control",
        )

    def test_non_local_env_without_config_raises(self):
        os.environ["CCE_ENVIRONMENT"] = "production"
        with self.assertRaisesRegex(RuntimeError, "CCE_CONTROL_DATABASE_CREDENTIAL_REF"):
            settings._build_database_url()

    def test_unset_environment_without_config_raises(self):
        with self.assertRaisesRegex(RuntimeError, "CCE_CONTROL_DATABASE_CREDENTIAL_REF"):
            settings._build_database_url()

    def test_explicit_control_url_wins_outside_local(self):
        os.environ["CCE_ENVIRONMENT"] = "production"
        os.environ["CCE_CONTROL_DATABASE_URL"] = "postgresql://user:pass@db:5432/cce"
        self.assertEqual(
            settings._build_database_url(), "postgresql://user:pass@db:5432/cce"
        )

    def test_credential_ref_takes_priority_and_can_hold_full_dsn(self):
        os.environ["CCE_ENVIRONMENT"] = "production"
        os.environ["CCE_CONTROL_DATABASE_URL"] = "postgresql://ignored"
        os.environ["CCE_CONTROL_DATABASE_CREDENTIAL_REF"] = "azure-kv://vault/cce-dsn"
        with mock.patch.object(
            settings, "load_credential", return_value="postgresql://u:p@db:5432/cce"
        ):
            self.assertEqual(
                settings._build_database_url(), "postgresql://u:p@db:5432/cce"
            )

    def test_credential_ref_can_hold_password_only(self):
        os.environ["CCE_ENVIRONMENT"] = "production"
        os.environ["CCE_CONTROL_DATABASE_CREDENTIAL_REF"] = "azure-kv://vault/cce-pw"
        os.environ["POSTGRES_USER"] = "cce_user"
        os.environ["POSTGRES_HOST"] = "postgres"
        os.environ["POSTGRES_PORT"] = "5432"
        os.environ["POSTGRES_DB"] = "cce_control"
        with mock.patch.object(settings, "load_credential", return_value="secret-pw"):
            self.assertEqual(
                settings._build_database_url(),
                "postgresql://cce_user:secret-pw@postgres:5432/cce_control",
            )
