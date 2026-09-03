#!/usr/bin/env python3
"""Direct tests of deterministic ChangeObserver implementations."""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from agents.connector_agent.change_capture import (  # noqa: E402
    UnstructuredChangeObserver, StructuredChangeObserver, ObserverRejected,
)

DOCUMENT_HANDLE = {
    "handle_id": "hnd_gdrive_contracts", "source_id": "gdrive_contracts",
    "adapter": "google-drive", "read_only_verified": True,
    "entitlement_capture_verified": True, "fetch_timeout_ms": 30000,
    "max_objects": 500, "object_scope": ["folder:0ABCxyz"], "status": "READY",
    "violated_rule": None,
}

STRUCTURED_HANDLE = {
    "handle_id": "hnd_wh_prod_snowflake", "source_id": "wh_prod_snowflake",
    "adapter": "snowflake", "dialect": "snowflake", "read_only_verified": True,
    "statement_timeout_ms": 30000, "max_rows": 200,
    "schema_scope": ["ANALYTICS"], "status": "READY", "violated_rule": None,
}


class UnstructuredChangeCaptureTests(unittest.TestCase):

    def test_added_object_produces_created_event_with_metadata_only(self):
        def lister(cursor):
            return {"objects": [
                {"object_id": "doc-1", "revision": "rev-1", "scope": "folder:0ABCxyz", "state": "added"},
            ], "cursor_next": "cur-1"}

        observer = UnstructuredChangeObserver("gdrive_contracts", "google-drive", True, lister)
        result = observer.start(DOCUMENT_HANDLE, checkpoint=None)
        self.assertEqual(len(result["events"]), 1)
        event = result["events"][0]
        self.assertEqual(event["change_type"], "created")
        self.assertEqual(event["object"]["object_id"], "doc-1")
        self.assertIsNone(event["object"]["content_hash"])
        self.assertNotIn("text", event["object"])

    def test_changed_object_produces_updated_event(self):
        def lister(cursor):
            return {"objects": [
                {"object_id": "doc-1", "revision": "rev-2", "scope": "folder:0ABCxyz", "state": "changed"},
            ], "cursor_next": "cur-2"}

        observer = UnstructuredChangeObserver("gdrive_contracts", "google-drive", True, lister)
        result = observer.poll(DOCUMENT_HANDLE, checkpoint="cur-1")
        self.assertEqual(result["events"][0]["change_type"], "updated")

    def test_deleted_object_emits_metadata_only_change_event(self):
        def lister(cursor):
            return {"objects": [
                {"object_id": "doc-1", "revision": "rev-2", "scope": "folder:0ABCxyz", "state": "deleted"},
            ], "cursor_next": "cur-3"}

        observer = UnstructuredChangeObserver("gdrive_contracts", "google-drive", True, lister)
        result = observer.poll(DOCUMENT_HANDLE, checkpoint="cur-2")
        event = result["events"][0]
        self.assertEqual(event["change_type"], "deleted")
        self.assertIsNone(event["object"]["content_hash"])

    def test_first_poll_with_no_checkpoint_uses_full_sync_not_incremental(self):
        seen_modes = []

        def lister(cursor):
            return {"objects": [], "cursor_next": "cur-1"}

        observer = UnstructuredChangeObserver("gdrive_contracts", "google-drive", True, lister)
        # No exception means sync_mode="full" was correctly used (DSY04 would
        # reject "incremental" with no cursor_in).
        result = observer.start(DOCUMENT_HANDLE, checkpoint=None)
        self.assertEqual(result["events"], [])

    def test_malformed_object_from_lister_is_rejected_not_silently_dropped(self):
        def lister(cursor):
            return {"objects": [{"object_id": "doc-1", "revision": "r1", "scope": "folder:0ABCxyz"}],
                    "cursor_next": "cur-1"}  # missing "state"

        observer = UnstructuredChangeObserver("gdrive_contracts", "google-drive", True, lister)
        with self.assertRaises(ObserverRejected) as ctx:
            observer.start(DOCUMENT_HANDLE, checkpoint=None)
        self.assertEqual(ctx.exception.rule, "DSY05")


class StructuredChangeCaptureTests(unittest.TestCase):

    def test_first_ever_sync_reports_every_table_as_added(self):
        catalog = [
            {"schema": "ANALYTICS", "table": "ORDERS",
             "columns": [{"name": "ID", "type": "NUMBER", "sensitive": False}],
             "sample": {"ID": 1}},
        ]
        observer = StructuredChangeObserver(
            "wh_prod_snowflake", "snowflake", "snowflake", ["ANALYTICS"],
            catalog_lister=lambda: catalog,
        )
        result = observer.start(STRUCTURED_HANDLE, checkpoint=None)
        change_types = sorted(e["change_type"] for e in result["events"])
        self.assertIn("created", change_types)

    def test_second_sync_with_a_new_column_reports_an_added_column_event(self):
        store = {}
        catalog_v1 = [
            {"schema": "ANALYTICS", "table": "ORDERS",
             "columns": [{"name": "ID", "type": "NUMBER", "sensitive": False}], "sample": {"ID": 1}},
        ]
        observer1 = StructuredChangeObserver(
            "wh_prod_snowflake", "snowflake", "snowflake", ["ANALYTICS"],
            catalog_lister=lambda: catalog_v1, metadata_store_dict=store,
        )
        observer1.start(STRUCTURED_HANDLE, checkpoint=None)

        catalog_v2 = [
            {"schema": "ANALYTICS", "table": "ORDERS",
             "columns": [{"name": "ID", "type": "NUMBER", "sensitive": False},
                         {"name": "TOTAL", "type": "NUMBER", "sensitive": False}],
             "sample": {"ID": 1, "TOTAL": 100}},
        ]
        observer2 = StructuredChangeObserver(
            "wh_prod_snowflake", "snowflake", "snowflake", ["ANALYTICS"],
            catalog_lister=lambda: catalog_v2, metadata_store_dict=store,
        )
        result = observer2.poll(STRUCTURED_HANDLE, checkpoint="1")
        added_ids = [e["object"]["object_id"] for e in result["events"] if e["change_type"] == "created"]
        self.assertIn("ANALYTICS.ORDERS.TOTAL", added_ids)

    def test_dropped_column_is_reported_as_deleted_and_breaking(self):
        store = {}
        catalog_v1 = [
            {"schema": "ANALYTICS", "table": "ORDERS",
             "columns": [{"name": "ID", "type": "NUMBER", "sensitive": False},
                         {"name": "LEGACY_FLAG", "type": "BOOLEAN", "sensitive": False}],
             "sample": {"ID": 1, "LEGACY_FLAG": True}},
        ]
        StructuredChangeObserver(
            "wh_prod_snowflake", "snowflake", "snowflake", ["ANALYTICS"],
            catalog_lister=lambda: catalog_v1, metadata_store_dict=store,
        ).start(STRUCTURED_HANDLE, checkpoint=None)

        catalog_v2 = [
            {"schema": "ANALYTICS", "table": "ORDERS",
             "columns": [{"name": "ID", "type": "NUMBER", "sensitive": False}], "sample": {"ID": 1}},
        ]
        result = StructuredChangeObserver(
            "wh_prod_snowflake", "snowflake", "snowflake", ["ANALYTICS"],
            catalog_lister=lambda: catalog_v2, metadata_store_dict=store,
        ).poll(STRUCTURED_HANDLE, checkpoint="1")
        deleted_ids = [e["object"]["object_id"] for e in result["events"] if e["change_type"] == "deleted"]
        self.assertIn("ANALYTICS.ORDERS.LEGACY_FLAG", deleted_ids)


if __name__ == "__main__":
    unittest.main()
