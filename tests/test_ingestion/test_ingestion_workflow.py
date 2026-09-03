#!/usr/bin/env python3
"""Node-level and full-graph tests for agents/ingestion_workflow.py.

No live Azure/Snowflake credentials required anywhere in this file --
fetch_unstructured_fn / fetch_structured_fn / sdk_emit_fn are always
injected fakes, the same fixture convention
agents/connector_agent/change_capture.py's observers already use for a
live driver read (object_lister/catalog_lister).
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from agents.ingestion_workflow import (  # noqa: E402
    route_by_source, fetch_unstructured_node, fetch_structured_node,
    parse_document_node, normalize_document_node, classify_for_dlp_node,
    redact_if_needed_node, emit_to_sdk_node, checkpoint_node,
    build_ingestion_workflow, run_ingestion,
)
from common.tools.checkpoint_manager import IngestionCheckpointStore  # noqa: E402


def make_event(object_id="notes.txt", adapter="azure-blob", kind="unstructured",
                change_type="created", version="rev-1"):
    return {
        "event_id": "e1", "trace_id": "trc_test", "tenant_id": "t1",
        "source": {"adapter": adapter, "kind": kind, "connection_handle": "h1"},
        "object": {"object_id": object_id, "object_type": "document",
                    "source_ref": "%s:%s" % (adapter, object_id),
                    "version": version, "content_hash": None, "modified_at": None},
        "change_type": change_type,
        "checkpoint": {"previous_cursor": None, "current_cursor": "cur-1"},
        "entitlement_state": "unknown",
    }


def base_state(**overrides):
    state = {
        "source_id": "src-1", "tenant_id": "t1", "kind": "unstructured", "adapter": "azure-blob",
        "connection_handle": {"handle_id": "h1"}, "event": make_event(), "schema_scope": [],
        "trace_id": "trc_test",
        "_fetch_unstructured": None, "_fetch_structured": None, "_sdk_emit": None,
        "_checkpoint_store": None,
        "raw_content": None, "parsed_doc": None, "normalized_doc": None,
        "dlp_verdict": None, "redacted_doc": None,
        "errors": [], "warnings": [], "ready_for_sdk": False, "sdk_response": None,
        "ingestion_checkpoint_id": None,
    }
    state.update(overrides)
    return state


class RouteTests(unittest.TestCase):

    def test_unstructured_created_routes_to_fetch_unstructured(self):
        state = route_by_source(base_state(kind="unstructured", event=make_event(change_type="created")))
        self.assertEqual(state["_next_node"], "fetch_unstructured")

    def test_structured_created_routes_to_fetch_structured(self):
        state = route_by_source(base_state(kind="structured", event=make_event(kind="structured", change_type="created")))
        self.assertEqual(state["_next_node"], "fetch_structured")

    def test_deleted_object_skips_straight_to_emit_regardless_of_kind(self):
        state = route_by_source(base_state(kind="structured", event=make_event(kind="structured", change_type="deleted")))
        self.assertEqual(state["_next_node"], "emit")


class FetchUnstructuredNodeTests(unittest.TestCase):

    def test_success_sets_raw_content(self):
        state = base_state(_fetch_unstructured=lambda a, h, o: b"hello")
        result = fetch_unstructured_node(state)
        self.assertEqual(result["raw_content"], b"hello")
        self.assertEqual(result["errors"], [])

    def test_missing_fetcher_records_error_and_continues(self):
        state = base_state(_fetch_unstructured=None)
        result = fetch_unstructured_node(state)
        self.assertIsNone(result["raw_content"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("fetch_unstructured", result["errors"][0])

    def test_fetcher_exception_is_captured_not_raised(self):
        def boom(a, h, o):
            raise ValueError("blob not found")
        state = base_state(_fetch_unstructured=boom)
        result = fetch_unstructured_node(state)
        self.assertIn("blob not found", result["errors"][0])


class FetchStructuredNodeTests(unittest.TestCase):

    def test_success_sets_raw_content(self):
        card = {"schema": "S", "tables": [{"name": "T", "columns": [{"name": "C", "type": "VARCHAR", "nullable": True}],
                                            "row_count": None, "sample_row": None}]}
        state = base_state(kind="structured", adapter="snowflake",
                            event=make_event(kind="structured"),
                            _fetch_structured=lambda a, h, s: card)
        result = fetch_structured_node(state)
        self.assertEqual(result["raw_content"], card)

    def test_no_injected_fetcher_and_no_default_for_this_adapter_records_error(self):
        # "postgres" has no default fetcher (only "snowflake" does) -- this
        # must fail fast with a clear error, not attempt any live I/O.
        state = base_state(kind="structured", adapter="postgres", event=make_event(kind="structured", adapter="postgres"))
        result = fetch_structured_node(state)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("no default fetcher", result["errors"][0])

    def test_no_injected_fetcher_uses_the_real_default_for_snowflake(self):
        # Verifies the production wiring (no live I/O -- snowflake_schema_fetcher
        # itself is replaced with a fake here).
        calls = []

        def fake_fetcher(adapter, handle, schema_scope):
            calls.append((adapter, handle, schema_scope))
            return {"schema": "S", "tables": []}

        with mock.patch("common.tools.source_connector.snowflake_schema_fetcher",
                                  return_value=fake_fetcher):
            state = base_state(kind="structured", adapter="snowflake", event=make_event(kind="structured"))
            result = fetch_structured_node(state)
        self.assertEqual(result["raw_content"], {"schema": "S", "tables": []})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "snowflake")


class ParseDocumentNodeTests(unittest.TestCase):

    def test_structured_kind_is_a_no_op(self):
        state = base_state(kind="structured", raw_content={"metadata": {}, "elements": []})
        result = parse_document_node(state)
        self.assertIsNone(result["parsed_doc"])

    def test_no_raw_content_is_a_no_op(self):
        state = base_state(raw_content=None)
        result = parse_document_node(state)
        self.assertIsNone(result["parsed_doc"])

    def test_plain_text_bytes_parse_into_canonical_document(self):
        state = base_state(event=make_event(object_id="notes.txt"),
                            raw_content=b"First paragraph.\n\nSecond paragraph.")
        result = parse_document_node(state)
        self.assertEqual(result["errors"], [])
        self.assertIsNotNone(result["parsed_doc"])
        elements = result["parsed_doc"]["elements"]
        self.assertEqual(len(elements), 2)
        self.assertEqual(elements[0]["text"], "First paragraph.")

    def test_unsupported_mime_type_records_error(self):
        state = base_state(event=make_event(object_id="archive.zip"),
                            raw_content=b"PK\x03\x04binarydata")
        result = parse_document_node(state)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("unsupported mime type", result["errors"][0])


class NormalizeDocumentNodeTests(unittest.TestCase):

    def test_unstructured_passes_parsed_doc_through(self):
        parsed = {"metadata": {"document_id": "d1"}, "elements": [{"id": "e1", "text": "hi"}]}
        state = base_state(kind="unstructured", parsed_doc=parsed)
        result = normalize_document_node(state)
        self.assertEqual(result["normalized_doc"], parsed)

    def test_structured_converts_raw_content(self):
        card = {"schema": "S", "tables": [{"name": "T", "columns": [{"name": "C", "type": "INT", "nullable": True}],
                                            "row_count": None, "sample_row": None}]}
        state = base_state(kind="structured", raw_content=card)
        result = normalize_document_node(state)
        self.assertEqual(result["normalized_doc"]["elements"][0]["text"], "T (1 columns)")


class ClassifyAndRedactNodeTests(unittest.TestCase):
    """dlp_classifier.py is currently a stub (always PUBLIC, no-op redact) --
    these tests assert the workflow wires block_verdicts correctly around
    that stub, not that real PII detection happens yet."""

    def test_classify_produces_a_block_verdict_per_text_element(self):
        doc = {"metadata": {}, "elements": [{"id": "e1", "text": "hello"}, {"id": "e2", "text": "world"}]}
        state = base_state(normalized_doc=doc)
        result = classify_for_dlp_node(state)
        self.assertEqual(result["dlp_verdict"]["sensitivity"], "PUBLIC")
        self.assertEqual(len(result["dlp_verdict"]["block_verdicts"]), 2)
        self.assertEqual({v["block_id"] for v in result["dlp_verdict"]["block_verdicts"]}, {"e1", "e2"})

    def test_classify_with_no_normalized_doc_is_a_no_op(self):
        state = base_state(normalized_doc=None)
        result = classify_for_dlp_node(state)
        self.assertIsNone(result["dlp_verdict"])

    def test_redact_without_a_verdict_passes_doc_through_unchanged(self):
        doc = {"metadata": {}, "elements": [{"id": "e1", "text": "hello"}]}
        state = base_state(normalized_doc=doc, dlp_verdict=None)
        result = redact_if_needed_node(state)
        self.assertEqual(result["redacted_doc"], doc)

    def test_redact_leaves_public_text_untouched(self):
        doc = {"metadata": {}, "elements": [{"id": "e1", "text": "hello"}]}
        state = classify_for_dlp_node(base_state(normalized_doc=doc))
        result = redact_if_needed_node(state)
        self.assertEqual(result["redacted_doc"]["elements"][0]["text"], "hello")


class EmitToSdkNodeTests(unittest.TestCase):

    def test_dry_run_when_no_sdk_endpoint_configured(self):
        os.environ.pop("CCE_SDK_ENDPOINT", None)
        doc = {"metadata": {"document_id": "notes.txt"}, "elements": [{"id": "e1", "text": "hello"}]}
        state = base_state(normalized_doc=doc)
        result = emit_to_sdk_node(state)
        self.assertTrue(result["ready_for_sdk"])
        self.assertEqual(result["sdk_response"]["status"], "dry_run")

    def test_injected_sdk_emit_receives_the_full_payload_shape(self):
        captured = {}

        def fake_emit(payload):
            captured.update(payload)
            return {"memory_id": "mem_1", "chunks_count": 2}

        doc = {"metadata": {"document_id": "notes.txt"}, "elements": [{"id": "e1", "text": "hello"}]}
        state = base_state(normalized_doc=doc, dlp_verdict={"sensitivity": "PUBLIC", "block_verdicts": []},
                            _sdk_emit=fake_emit)
        result = emit_to_sdk_node(state)
        self.assertTrue(result["ready_for_sdk"])
        self.assertEqual(result["sdk_response"], {"memory_id": "mem_1", "chunks_count": 2})
        self.assertEqual(captured["document_id"], "notes.txt")
        self.assertEqual(captured["source_id"], "src-1")
        self.assertEqual(captured["blocks"], doc["elements"])
        self.assertEqual(captured["trace_id"], "trc_test")

    def test_deletion_payload_carries_no_blocks(self):
        captured = {}

        def fake_emit(payload):
            captured.update(payload)
            return {"status": "deleted"}

        state = base_state(event=make_event(change_type="deleted"), normalized_doc=None, _sdk_emit=fake_emit)
        result = emit_to_sdk_node(state)
        self.assertTrue(result["ready_for_sdk"])
        self.assertEqual(captured["change_type"], "deleted")
        self.assertEqual(captured["blocks"], [])

    def test_emit_failure_is_recorded_as_an_error_not_raised(self):
        def boom(payload):
            raise RuntimeError("SDK unreachable")
        state = base_state(_sdk_emit=boom)
        result = emit_to_sdk_node(state)
        self.assertFalse(result["ready_for_sdk"])
        self.assertIn("SDK unreachable", result["errors"][0])


class CheckpointNodeTests(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = IngestionCheckpointStore(store_path=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_saves_to_the_injected_store_and_records_the_checkpoint_id(self):
        state = base_state(_checkpoint_store=self.store, errors=[], ready_for_sdk=True)
        result = checkpoint_node(state)
        self.assertEqual(result["ingestion_checkpoint_id"], "src-1__notes.txt")
        loaded = self.store.load("src-1", "notes.txt")
        self.assertEqual(loaded["status"], "success")

    def test_status_is_partial_when_errors_present(self):
        state = base_state(_checkpoint_store=self.store, errors=["fetch_unstructured: boom"])
        result = checkpoint_node(state)
        loaded = self.store.load("src-1", "notes.txt")
        self.assertEqual(loaded["status"], "partial")


class FullWorkflowTests(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = IngestionCheckpointStore(store_path=self.tmpdir)
        os.environ.pop("CCE_SDK_ENDPOINT", None)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_graph_compiles(self):
        graph = build_ingestion_workflow()
        self.assertIsNotNone(graph)

    def test_full_unstructured_document_reaches_ready_for_sdk(self):
        event = make_event(object_id="contract.txt")
        success, state = run_ingestion(
            event, {"handle_id": "h1"}, source_id="azure-blob-contracts",
            fetch_unstructured_fn=lambda a, h, o: b"Rate 50%.\n\nDiscount applies to all customers.",
            checkpoint_store=self.store,
        )
        self.assertTrue(success)
        self.assertEqual(state["errors"], [])
        self.assertTrue(state["ready_for_sdk"])
        self.assertEqual(len(state["normalized_doc"]["elements"]), 2)
        self.assertEqual(state["ingestion_checkpoint_id"], "azure-blob-contracts__contract.txt")

    def test_full_structured_schema_card_reaches_ready_for_sdk(self):
        event = make_event(object_id="ANALYTICS.CUSTOMERS", adapter="snowflake", kind="structured")
        card = {"schema": "ANALYTICS",
                "tables": [{"name": "CUSTOMERS",
                            "columns": [{"name": "EMAIL", "type": "VARCHAR", "nullable": True}],
                            "row_count": 10, "sample_row": {"EMAIL": "a@b.com"}}]}
        success, state = run_ingestion(
            event, {"handle_id": "h1"}, source_id="snowflake-prod",
            fetch_structured_fn=lambda a, h, s: card,
            checkpoint_store=self.store,
        )
        self.assertTrue(success)
        self.assertIsNone(state["parsed_doc"])  # structured lane never parses
        self.assertEqual(state["normalized_doc"]["elements"][0]["text"], "CUSTOMERS (1 columns)")

    def test_deleted_event_skips_fetch_and_still_checkpoints(self):
        event = make_event(object_id="old.txt", change_type="deleted")
        success, state = run_ingestion(
            event, {"handle_id": "h1"}, source_id="azure-blob-contracts",
            checkpoint_store=self.store,
        )
        self.assertTrue(success)
        self.assertIsNone(state["raw_content"])
        self.assertTrue(state["ready_for_sdk"])
        self.assertIsNotNone(state["ingestion_checkpoint_id"])

    def test_a_failed_fetch_still_reaches_checkpoint_with_success_false(self):
        event = make_event(object_id="missing.txt")
        success, state = run_ingestion(
            event, {"handle_id": "h1"}, source_id="azure-blob-contracts",
            fetch_unstructured_fn=None,  # no fetcher -> fetch_unstructured records an error
            checkpoint_store=self.store,
        )
        self.assertFalse(success)
        self.assertGreaterEqual(len(state["errors"]), 1)
        loaded = self.store.load("azure-blob-contracts", "missing.txt")
        self.assertEqual(loaded["status"], "partial")

    def test_trace_id_defaults_from_the_event_when_not_passed_explicitly(self):
        event = make_event(object_id="notes.txt")
        success, state = run_ingestion(
            event, {"handle_id": "h1"}, source_id="azure-blob-contracts",
            fetch_unstructured_fn=lambda a, h, o: b"hi",
            checkpoint_store=self.store,
        )
        self.assertEqual(state["trace_id"], event["trace_id"])


if __name__ == "__main__":
    unittest.main()
