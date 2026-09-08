import os
import unittest
from unittest import mock

from cce.config import settings


class SettingsDatabaseUrlTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

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


class AgenticPlaneSettingsTests(unittest.TestCase):
    def test_agentic_plane_requires_endpoint_and_key(self):
        with mock.patch.object(settings, "load_dotenv"), mock.patch.dict(
            os.environ,
            {"CCE_ENVIRONMENT": "local", "CCE_INDEX_BACKEND": "agentic_plane"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "CCE_AGENTICPLANE_BASE_URL, CCE_AGENTICPLANE_API_KEY",
            ):
                settings.load_settings()

    def test_agentic_plane_resolves_key_reference_and_reads_tuning(self):
        environment = {
            "CCE_ENVIRONMENT": "local",
            "CCE_INDEX_BACKEND": "agentic_plane",
            "CCE_AGENTICPLANE_BASE_URL": "https://plane.example",
            "CCE_AGENTICPLANE_API_KEY": "env://PLANE_KEY",
            "CCE_AGENTICPLANE_TIMEOUT": "41",
            "CCE_AGENTICPLANE_MAX_RETRIES": "6",
            "CCE_AGENTICPLANE_AGENT_ID": "cce-prod-ingestion",
        }
        with mock.patch.object(settings, "load_dotenv"), mock.patch.dict(
            os.environ, environment, clear=True
        ), mock.patch.object(settings, "load_credential", return_value="ap_resolved") as load:
            loaded = settings.load_settings()

        load.assert_called_once_with("env://PLANE_KEY")
        self.assertEqual(loaded.agenticplane_base_url, "https://plane.example")
        self.assertEqual(loaded.agenticplane_api_key, "ap_resolved")
        self.assertEqual(loaded.agenticplane_timeout, 41)
        self.assertEqual(loaded.agenticplane_max_retries, 6)
        self.assertEqual(loaded.agenticplane_agent_id, "cce-prod-ingestion")
        self.assertNotIn("ap_resolved", repr(loaded))

    def test_agentic_plane_accepts_raw_api_key_and_defaults(self):
        environment = {
            "CCE_ENVIRONMENT": "local",
            "CCE_INDEX_BACKEND": "agentic_plane",
            "CCE_AGENTICPLANE_BASE_URL": "https://plane.example",
            "CCE_AGENTICPLANE_API_KEY": "ap_raw",
        }
        with mock.patch.object(settings, "load_dotenv"), mock.patch.dict(
            os.environ, environment, clear=True
        ), mock.patch.object(settings, "load_credential") as load:
            loaded = settings.load_settings()

        load.assert_not_called()
        self.assertEqual(loaded.agenticplane_api_key, "ap_raw")
        self.assertEqual(loaded.agenticplane_timeout, 30)
        self.assertEqual(loaded.agenticplane_max_retries, 3)
        self.assertEqual(loaded.agenticplane_agent_id, "cce-ingestion")
