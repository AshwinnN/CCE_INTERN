#!/usr/bin/env python3
"""Contract-shape tests for the Connector Agent's request/response/event DTOs."""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from agents.connector_agent.contracts import ConnectorRequest, SourceChangeEvent  # noqa: E402


class ContractTests(unittest.TestCase):

    def test_connector_request_from_dict_round_trips(self):
        raw = {
            "request_id": "req-1", "tenant_id": "t1", "source_adapter": "snowflake",
            "credential_ref": "vault://cce/wh", "requested_capabilities": ["schema_scope"],
            "source_scope": {"database": "ANALYTICS"},
            "observation": {"mode": "start", "checkpoint": None},
        }
        req = ConnectorRequest.from_dict(raw)
        self.assertEqual(req.tenant_id, "t1")
        self.assertEqual(req.source_adapter, "snowflake")
        self.assertEqual(req.observation.mode, "start")

    def test_connector_request_defaults_when_optional_fields_absent(self):
        req = ConnectorRequest.from_dict({
            "tenant_id": "t1", "source_adapter": "snowflake", "credential_ref": "vault://cce/wh",
        })
        self.assertEqual(req.requested_capabilities, [])
        self.assertEqual(req.source_scope, {})
        self.assertIsNone(req.observation.mode)

    def test_source_change_event_idempotency_key_is_stable_and_specific(self):
        event = SourceChangeEvent(
            event_id="e1", trace_id="trc-1", tenant_id="t1",
            source={"adapter": "google-drive", "kind": "unstructured", "connection_handle": "hnd_x"},
            object={"object_id": "obj-1", "object_type": "document", "source_ref": "r",
                    "version": "rev-1", "content_hash": None, "modified_at": None},
            change_type="created",
            checkpoint={"previous_cursor": None, "current_cursor": "c1"},
        )
        key1 = event.idempotency_key()
        key2 = event.idempotency_key()
        self.assertEqual(key1, key2)
        self.assertIn("t1", key1)
        self.assertIn("google-drive", key1)
        self.assertIn("obj-1", key1)
        self.assertIn("created", key1)

    def test_source_change_event_never_carries_content_fields(self):
        event = SourceChangeEvent(
            event_id="e1", trace_id="trc-1", tenant_id="t1",
            source={"adapter": "snowflake", "kind": "structured", "connection_handle": "hnd_x"},
            object={"object_id": "ANALYTICS.T1", "object_type": "table", "source_ref": "r",
                    "version": "2", "content_hash": None, "modified_at": None},
            change_type="updated",
            checkpoint={"previous_cursor": "1", "current_cursor": "2"},
        )
        d = event.to_dict()
        self.assertIsNone(d["object"]["content_hash"])
        self.assertNotIn("rows", d["object"])
        self.assertNotIn("text", d["object"])
        self.assertNotIn("body", d["object"])


if __name__ == "__main__":
    unittest.main()
