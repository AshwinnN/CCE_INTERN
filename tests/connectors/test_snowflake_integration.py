#!/usr/bin/env python3
"""Live integration test: connects to the real Snowflake account in .env
through connectors.snowflake.SnowflakeConnector -- proves this package's
real write-probe and real schema discovery actually work against a live
warehouse, the same way tools/verify_snowflake_connection.py already
proved it standalone. Skips (does not fail) when CCE_SNOWFLAKE_ENABLED
isn't "true", matching tests/test_ingestion/test_canonical_model.py's
convention for the Azure Blob live test.

Run:  .venv/bin/python3 tests/connectors/test_snowflake_integration.py
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(REPO, ".env"))

from connectors.factory import ConnectorFactory  # noqa: E402
from connectors.snowflake.config import build_config_from_env  # noqa: E402


@unittest.skipUnless(
    os.environ.get("CCE_SNOWFLAKE_ENABLED", "false").lower() == "true",
    "CCE_SNOWFLAKE_ENABLED is not 'true' -- skipping live Snowflake test",
)
class SnowflakeLiveIntegrationTests(unittest.TestCase):

    def test_connect_proves_read_only_and_fetches_a_real_schema_card(self):
        config = build_config_from_env()
        connector = ConnectorFactory.create(config)

        connection = connector.connect()
        try:
            self.assertTrue(connection.read_only_verified)

            card = connector.get_schema_card(config.schema, max_tables=3)
            self.assertEqual(card["schema"], config.schema)
            self.assertIsInstance(card["tables"], list)
            for table in card["tables"]:
                self.assertIn("name", table)
                self.assertIn("columns", table)
                for col in table["columns"]:
                    self.assertIn("name", col)
                    self.assertIn("type", col)
        finally:
            connector.close()


if __name__ == "__main__":
    unittest.main()
