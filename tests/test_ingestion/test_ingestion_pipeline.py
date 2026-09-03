#!/usr/bin/env python3
"""agents/ingestion_pipeline.py tests.

A stub connector agent (implementing only .handle()) stands in for the real
ConnectorAgent here -- exercising the real one's observation mode requires
skill scripts (skill-document-sync/etc.) that aren't present in every
checkout (see agents/connector_agent/README.md's "Known gaps" #5; those
skills are documented but have no scripts/ directory yet). That gap is
pre-existing and orthogonal to this module: run_pipeline() takes
`connector_agent` as an injected dependency specifically so its own
fan-out logic can be tested independently of which ConnectorAgent
implementation supplies the events. RealConnectorAgentConnectOnlyTests below
does exercise the real ConnectorAgent for the one call shape that needs no
skill scripts AND no live credentials: a connect-only, unstructured-lane
call (skill-document-source-connect is a zero-I/O profile validator, not a
live connect -- see agents/connector_agent/README.md). The structured lane
would also work here, but connect_structured() now does real, live I/O by
default (see connectors/snowflake/connector.py) and would need an injected
structured_connector_factory the same way
tests/connector_agent/test_connector_agent.py does; the unstructured lane
avoids that entirely, which is a better fit for this module's own tests.
"""
import os
import shutil
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from agents.connector_agent.agent import ConnectorAgent  # noqa: E402
from agents.connector_agent.contracts import ConnectorRequest, ConnectorResponse  # noqa: E402
from agents.ingestion_pipeline import run_pipeline  # noqa: E402
from common.tools.checkpoint_manager import IngestionCheckpointStore  # noqa: E402


def make_request(**overrides):
    base = dict(
        tenant_id="t1", source_adapter="azure-blob", credential_ref="vault://cce/blob",
        request_id="req-1", requested_capabilities=[], source_scope={"source_id": "azure-blob-contracts"},
        observation={},
    )
    base.update(overrides)
    return ConnectorRequest.from_dict(base)


def make_event(object_id, change_type="created", adapter="azure-blob", kind="unstructured"):
    return {
        "event_id": "e-%s" % object_id, "trace_id": "trc_test", "tenant_id": "t1",
        "source": {"adapter": adapter, "kind": kind, "connection_handle": "h1"},
        "object": {"object_id": object_id, "object_type": "document",
                    "source_ref": "%s:%s" % (adapter, object_id),
                    "version": "rev-1", "content_hash": None, "modified_at": None},
        "change_type": change_type,
        "checkpoint": {"previous_cursor": None, "current_cursor": "cur-1"},
        "entitlement_state": "unknown",
    }


class StubConnectorAgent:
    """Implements only .handle() -- the one surface run_pipeline() depends
    on -- so this test controls exactly which change_events flow into
    ingestion without needing the real observation stage's skill scripts."""

    def __init__(self, response: ConnectorResponse):
        self._response = response

    def handle(self, request: ConnectorRequest) -> ConnectorResponse:
        return self._response


def observing_response(events):
    return ConnectorResponse(
        trace_id="trc_test", request_id="req-1", status="observing",
        source={"adapter": "azure-blob", "kind": "unstructured", "dialect": None},
        connection={"connection_handle": "h1", "observation_handle": "obs_h1",
                    "credential_ref_present": True, "lease_valid": True, "read_only_verified": True},
        capabilities=[], skill_trace=[], checkpoint="cur-1", error=None,
        change_events=events,
    )


class RunPipelineFanOutTests(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = IngestionCheckpointStore(store_path=self.tmpdir)
        os.environ.pop("CCE_SDK_ENDPOINT", None)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_change_events_yields_no_ingestion_results(self):
        agent = StubConnectorAgent(observing_response([]))
        result = run_pipeline(make_request(), connector_agent=agent, checkpoint_store=self.store)
        self.assertEqual(result.ingestion_results, [])
        self.assertEqual(result.connector_response.status, "observing")

    def test_each_change_event_produces_one_ingestion_outcome(self):
        events = [make_event("a.txt"), make_event("b.txt", change_type="updated")]
        agent = StubConnectorAgent(observing_response(events))
        result = run_pipeline(
            make_request(), connector_agent=agent, checkpoint_store=self.store,
            fetch_unstructured_fn=lambda a, h, o: b"paragraph one\n\nparagraph two",
        )
        self.assertEqual(len(result.ingestion_results), 2)
        self.assertEqual([r.object_id for r in result.ingestion_results], ["a.txt", "b.txt"])
        self.assertTrue(all(r.success for r in result.ingestion_results))
        self.assertEqual(result.ingestion_results[1].change_type, "updated")

    def test_a_deletion_event_is_ingested_without_a_fetcher(self):
        agent = StubConnectorAgent(observing_response([make_event("old.txt", change_type="deleted")]))
        result = run_pipeline(make_request(), connector_agent=agent, checkpoint_store=self.store)
        self.assertEqual(len(result.ingestion_results), 1)
        self.assertTrue(result.ingestion_results[0].success)

    def test_ingestion_failure_is_reported_per_event_not_raised(self):
        agent = StubConnectorAgent(observing_response([make_event("unfetchable.txt")]))
        result = run_pipeline(make_request(), connector_agent=agent, checkpoint_store=self.store)
        outcome = result.ingestion_results[0]
        self.assertFalse(outcome.success)
        self.assertGreaterEqual(len(outcome.errors), 1)

    def test_to_dict_round_trips_both_connector_and_ingestion_shapes(self):
        agent = StubConnectorAgent(observing_response([make_event("a.txt")]))
        result = run_pipeline(
            make_request(), connector_agent=agent, checkpoint_store=self.store,
            fetch_unstructured_fn=lambda a, h, o: b"hello",
        )
        d = result.to_dict()
        self.assertIn("connector_response", d)
        self.assertIn("ingestion_results", d)
        self.assertEqual(d["ingestion_results"][0]["object_id"], "a.txt")


class RealConnectorAgentConnectOnlyTests(unittest.TestCase):
    """Exercises the real ConnectorAgent for the one call shape that needs
    no skill scripts and no live credentials (connect-only, unstructured,
    no observation) -- confirms run_pipeline() composes with it correctly."""

    def test_connect_only_request_yields_no_change_events_and_no_ingestion(self):
        agent = ConnectorAgent()
        result = run_pipeline(make_request(source_adapter="google-drive", credential_ref="vault://cce/gdrive",
                                            source_scope={"object_scope": ["folder:x"]}),
                               connector_agent=agent)
        self.assertEqual(result.connector_response.status, "connected")
        self.assertEqual(result.connector_response.change_events, [])
        self.assertEqual(result.ingestion_results, [])


if __name__ == "__main__":
    unittest.main()
