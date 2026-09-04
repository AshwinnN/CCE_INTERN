#!/usr/bin/env python3
import os
import sys
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from cce.connectors.fetch import (  # noqa: E402
    fetch_unstructured, fetch_structured, azure_blob_fetcher, snowflake_schema_fetcher,
)


class FetchUnstructuredTests(unittest.TestCase):

    def test_delegates_to_injected_fetcher_with_adapter_handle_and_object_id(self):
        calls = []

        def fetcher(adapter, handle, object_id):
            calls.append((adapter, handle, object_id))
            return b"raw-bytes"

        result = fetch_unstructured("azure-blob", {"handle_id": "h1"}, "notes.txt", fetcher)
        self.assertEqual(result, b"raw-bytes")
        self.assertEqual(calls, [("azure-blob", {"handle_id": "h1"}, "notes.txt")])

    def test_raises_when_no_fetcher_configured(self):
        with self.assertRaises(RuntimeError):
            fetch_unstructured("azure-blob", {"handle_id": "h1"}, "notes.txt", None)


class FetchStructuredTests(unittest.TestCase):

    def test_delegates_to_injected_fetcher_with_schema_scope(self):
        calls = []

        def fetcher(adapter, handle, schema_scope):
            calls.append((adapter, handle, schema_scope))
            return {"metadata": {}, "elements": []}

        result = fetch_structured("snowflake", {"handle_id": "h1"}, ["PUBLIC"], fetcher)
        self.assertEqual(result, {"metadata": {}, "elements": []})
        self.assertEqual(calls, [("snowflake", {"handle_id": "h1"}, ["PUBLIC"])])

    def test_raises_when_no_fetcher_configured(self):
        with self.assertRaises(RuntimeError):
            fetch_structured("snowflake", {"handle_id": "h1"}, [], None)


class AzureBlobFetcherTests(unittest.TestCase):

    def test_rejects_a_non_azure_blob_adapter(self):
        fetcher = azure_blob_fetcher("DefaultEndpointsProtocol=https;AccountName=x;AccountKey=y;", "container")
        with self.assertRaises(ValueError):
            fetcher("google-drive", {"handle_id": "h1"}, "obj-1")


class SnowflakeSchemaFetcherTests(unittest.TestCase):
    """No live Snowflake I/O -- ConnectorFactory.create is mocked to a fake
    connector, matching the injected-driver convention
    tests/connectors/test_snowflake_connector.py already establishes."""

    def test_rejects_a_non_snowflake_adapter(self):
        fetcher = snowflake_schema_fetcher()
        with self.assertRaises(ValueError):
            fetcher("postgres", {"handle_id": "h1"}, [])

    def test_connects_fetches_the_schema_card_and_always_closes(self):
        calls = {"connect": 0, "close": 0}

        class FakeConnector:
            def __init__(self, config):
                self.config = config

            def connect(self):
                calls["connect"] += 1

            def get_schema_card(self, schema, max_tables=None):
                return {"schema": schema, "tables": [], "_max_tables": max_tables}

            def close(self):
                calls["close"] += 1

        fake_config = mock.Mock(schema="PUBLIC")
        with mock.patch("cce.connectors.structured.snowflake.config.build_config_from_env", return_value=fake_config), \
             mock.patch("cce.connectors.factory.ConnectorFactory.create", return_value=FakeConnector(fake_config)):
            fetcher = snowflake_schema_fetcher(max_tables=5)
            card = fetcher("snowflake", {"handle_id": "h1"}, ["PUBLIC"])

        self.assertEqual(card, {"schema": "PUBLIC", "tables": [], "_max_tables": 5})
        self.assertEqual(calls, {"connect": 1, "close": 1})

    def test_closes_the_connector_even_when_get_schema_card_raises(self):
        class FailingConnector:
            def __init__(self, config):
                pass

            def connect(self):
                pass

            def get_schema_card(self, schema, max_tables=None):
                raise RuntimeError("no read grant")

            def close(self):
                calls["close"] += 1

        calls = {"close": 0}
        fake_config = mock.Mock(schema="PUBLIC")
        with mock.patch("cce.connectors.structured.snowflake.config.build_config_from_env", return_value=fake_config), \
             mock.patch("cce.connectors.factory.ConnectorFactory.create", return_value=FailingConnector(fake_config)):
            fetcher = snowflake_schema_fetcher()
            with self.assertRaises(RuntimeError):
                fetcher("snowflake", {"handle_id": "h1"}, [])
        self.assertEqual(calls["close"], 1)


if __name__ == "__main__":
    unittest.main()
