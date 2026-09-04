#!/usr/bin/env python3
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from cce.connectors.base.generic_source import DeterministicSourceConnector  # noqa: E402


class DeterministicSourceConnectorTests(unittest.TestCase):

    def test_connect_lists_objects_and_fetches_bytes_through_injected_readers(self):
        connector = DeterministicSourceConnector(
            source_id="drive-contracts",
            adapter="google-drive",
            object_lister=lambda cursor: {"objects": [{"object_id": "doc-1"}], "cursor_next": "cur-1"},
            object_fetcher=lambda object_id: b"content for " + object_id.encode(),
        )
        connection = connector.connect()

        self.assertTrue(connection.read_only_verified)
        self.assertEqual(connection.source_id, "drive-contracts")
        self.assertEqual(connector.list_objects(None)["cursor_next"], "cur-1")
        self.assertEqual(connector.fetch_object("doc-1"), b"content for doc-1")

    def test_reader_methods_require_connect_first(self):
        connector = DeterministicSourceConnector("drive-contracts", "google-drive")

        with self.assertRaises(RuntimeError):
            connector.list_objects(None)
        with self.assertRaises(RuntimeError):
            connector.fetch_object("doc-1")


if __name__ == "__main__":
    unittest.main()
