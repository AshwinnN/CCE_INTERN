#!/usr/bin/env python3
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from connectors.base.exceptions import UnsupportedAdapterError  # noqa: E402
from connectors.base.models import ConnectionConfig  # noqa: E402
from connectors.factory import ConnectorFactory  # noqa: E402
from connectors.snowflake.connector import SnowflakeConnector  # noqa: E402


def make_config(adapter="snowflake"):
    return ConnectionConfig(adapter=adapter, account_id="acct", user="u",
                             credential_ref="env://X", database="D", schema="S")


class ConnectorFactoryTests(unittest.TestCase):

    def test_creates_a_snowflake_connector_for_the_snowflake_adapter(self):
        connector = ConnectorFactory.create(make_config("snowflake"))
        self.assertIsInstance(connector, SnowflakeConnector)

    def test_unknown_adapter_raises_unsupported_adapter_error(self):
        with self.assertRaises(UnsupportedAdapterError):
            ConnectorFactory.create(make_config("some-future-warehouse"))

    def test_register_adds_a_new_adapter_without_touching_existing_ones(self):
        class FakeConnector:
            def __init__(self, config):
                self.config = config

        ConnectorFactory.register("fake-db", FakeConnector)
        try:
            connector = ConnectorFactory.create(make_config("fake-db"))
            self.assertIsInstance(connector, FakeConnector)
            # snowflake registration is untouched by registering a new adapter
            self.assertIsInstance(ConnectorFactory.create(make_config("snowflake")), SnowflakeConnector)
        finally:
            del ConnectorFactory._connectors["fake-db"]


if __name__ == "__main__":
    unittest.main()
