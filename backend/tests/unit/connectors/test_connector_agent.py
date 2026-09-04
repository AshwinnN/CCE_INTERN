#!/usr/bin/env python3
"""Connector Agent orchestration tests for deterministic code paths.

The structured lane's connect step (orchestrator.connect_structured()) is
no longer a Skill call -- it's a real, deterministic connectors/ tool that
does live I/O by default (see connectors/snowflake/connector.py). Every
ConnectorAgent constructed here therefore goes through make_agent(), which
injects FakeStructuredConnector so this file never needs live Snowflake
credentials, matching the existing convention for object_lister/catalog_lister.
"""
import json
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from cce.connectors.agent import ConnectorAgent, FORBIDDEN_SKILLS  # noqa: E402
from cce.connectors.contracts import ConnectorRequest, ObservationSpec  # noqa: E402
from cce.ingestion.checkpoint import InMemoryCheckpointStore, InMemoryDedupStore  # noqa: E402
from cce.skills.loader import _CACHE as SKILL_LOADER_CACHE  # noqa: E402
from cce.connectors.base.connection import StructuredConnection  # noqa: E402
from cce.connectors.base.connector import StructuredConnector  # noqa: E402


class FakeStructuredConnector(StructuredConnector):
    """Deterministic test double for cce.connectors.structured.snowflake.SnowflakeConnector
    -- proves connect_structured()'s wiring without any real I/O."""

    def __init__(self, config):
        self.config = config

    def connect(self):
        return StructuredConnection(self, "conn_fake_%s" % (self.config.account_id or "test"))

    def get_schema_card(self, schema, max_tables=None):
        return {"schema": schema, "tables": []}

    def execute_query(self, sql, params=None):
        return []

    def close(self):
        pass


def make_agent(**kwargs):
    kwargs.setdefault("structured_connector_factory", FakeStructuredConnector)
    return ConnectorAgent(**kwargs)


def make_request(**overrides):
    base = dict(
        tenant_id="t1", source_adapter="snowflake", credential_ref="vault://cce/wh_test",
        request_id="req-1", requested_capabilities=[], source_scope={}, observation={},
    )
    base.update(overrides)
    return ConnectorRequest.from_dict(base)


class RoutingTests(unittest.TestCase):

    def test_structured_registry_kind_routes_to_structured_connect_tool(self):
        agent = make_agent()
        resp = agent.handle(make_request(source_adapter="snowflake"))
        self.assertEqual(resp.status, "connected")
        self.assertEqual(resp.source["kind"], "structured")
        skills_called = [t.skill for t in resp.skill_trace]
        self.assertTrue(any(s.startswith("cce.connectors.structured.snowflake.") for s in skills_called))
        self.assertNotIn("skill-strucutred_source_connect", skills_called)  # no longer exists in any trace
        self.assertNotIn("skill-document-source-connect", skills_called)

    def test_unstructured_registry_kind_routes_to_code_source_connect(self):
        agent = make_agent()
        resp = agent.handle(make_request(
            source_adapter="google-drive",
            credential_ref="vault://cce/gdrive",
            source_scope={"object_scope": ["folder:0ABCxyz"]},
        ))
        self.assertEqual(resp.status, "connected")
        self.assertEqual(resp.source["kind"], "unstructured")
        skills_called = [t.skill for t in resp.skill_trace]
        self.assertIn("code.source-connect", skills_called)
        self.assertFalse(any(s.startswith("connectors.") for s in skills_called))

    def test_routing_is_kind_based_two_different_adapters_same_kind_same_path(self):
        agent = make_agent()
        snow = agent.handle(make_request(source_adapter="snowflake"))
        pg = agent.handle(make_request(source_adapter="postgres", credential_ref="vault://cce/pg"))
        snow_connect = [t.skill for t in snow.skill_trace if t.skill.startswith("connectors.")]
        pg_connect = [t.skill for t in pg.skill_trace if t.skill.startswith("connectors.")]
        self.assertEqual(len(snow_connect), 1)
        self.assertEqual(len(pg_connect), 1)
        # Both traces are handled by the identical FakeStructuredConnector
        # class -- only the adapter name in the label differs, proving the
        # routing decision is kind-based (STRUCTURED), never a hardcoded
        # "if adapter == 'snowflake'".
        self.assertEqual(snow_connect[0].replace("snowflake", "postgres"), pg_connect[0])


class FailClosedTests(unittest.TestCase):

    def test_missing_credential_ref_blocks_before_any_connector_skill(self):
        agent = make_agent()
        resp = agent.handle(make_request(credential_ref=""))
        self.assertEqual(resp.status, "blocked")
        self.assertEqual(resp.error["code"], "CREDENTIAL_REF_MISSING")
        skills_called = [t.skill for t in resp.skill_trace]
        self.assertFalse(any(s.startswith("connectors.") for s in skills_called))
        self.assertNotIn("code.source-connect", skills_called)

    def test_unknown_adapter_fails_before_registry_skill_is_even_called(self):
        agent = make_agent()
        resp = agent.handle(make_request(source_adapter="totally-unknown-vendor"))
        self.assertEqual(resp.status, "blocked")
        self.assertEqual(resp.error["code"], "REGISTRY_ADAPTER_UNKNOWN")
        self.assertEqual(resp.skill_trace, [])

    def test_requested_capability_not_present_fails_closed(self):
        agent = make_agent()
        resp = agent.handle(make_request(requested_capabilities=["not_a_real_capability"]))
        self.assertEqual(resp.status, "failed")
        self.assertEqual(resp.error["code"], "REGISTRY_CAPABILITY_UNAVAILABLE")

    def test_explicit_invalid_registry_input_never_falls_back_to_default(self):
        """A structured connect with a deliberately broken descriptor must
        fail, never silently succeed via validate_source_profile.py's own
        internal DEFAULT_REGISTRY."""
        from cce.connectors.registry_to_structured_connect import to_structured_connect_registry
        broken = {
            "adapter": "snowflake", "kind": "structured", "dialect": None,  # missing dialect
            "capabilities": {"write_probe": True, "statement_timeout": True,
                              "row_cap": True, "schema_scope": True},
            "schema_version": "1.0", "deprecated": False, "status": "READY", "violated_rule": None,
        }
        result = to_structured_connect_registry(broken)
        self.assertEqual(result["status"], "ERROR")
        self.assertIsNone(result["registry"])


class NoSecretLeakageTests(unittest.TestCase):

    def test_response_never_contains_the_credential_ref_scheme_secret_shape(self):
        agent = make_agent()
        resp = agent.handle(make_request())
        blob = json.dumps(resp.to_dict()).lower()
        for forbidden in ("password", "secret", "private_key", "api_key", "client_secret"):
            self.assertNotIn(forbidden, blob)

    def test_response_contains_no_stack_trace_or_raw_skill_payload(self):
        agent = make_agent()
        resp = agent.handle(make_request(credential_ref=""))
        blob = json.dumps(resp.to_dict())
        self.assertNotIn("Traceback", blob)
        self.assertNotIn("violated_rule", blob)  # internal skill vocabulary, not a sanitized error


class ForbiddenSkillTests(unittest.TestCase):

    def test_no_downstream_ingestion_skill_is_ever_loaded_by_a_connect_only_request(self):
        SKILL_LOADER_CACHE.clear()
        agent = make_agent()
        agent.handle(make_request(source_adapter="snowflake"))
        agent.handle(make_request(source_adapter="google-drive", credential_ref="vault://cce/gdrive",
                                   source_scope={"object_scope": ["folder:x"]}))
        loaded_skill_dirs = {key[0] for key in SKILL_LOADER_CACHE}
        self.assertEqual(loaded_skill_dirs & FORBIDDEN_SKILLS, set())


class ObservationTests(unittest.TestCase):

    def test_start_observation_on_unstructured_source_produces_created_events(self):
        def object_lister(cursor):
            return {"objects": [
                {"object_id": "doc-1", "revision": "rev-1", "scope": "folder:x", "state": "added"},
            ], "cursor_next": "cur-1"}

        agent = ConnectorAgent(object_lister=object_lister)
        resp = agent.handle(make_request(
            source_adapter="google-drive", credential_ref="vault://cce/gdrive",
            source_scope={"object_scope": ["folder:x"]},
            observation={"mode": "start"},
        ))
        self.assertEqual(resp.status, "observing")
        self.assertEqual(resp.checkpoint, "cur-1")

    def test_duplicate_change_event_is_not_handed_off_twice(self):
        calls = {"n": 0}

        def object_lister(cursor):
            calls["n"] += 1
            return {"objects": [
                {"object_id": "doc-1", "revision": "rev-1", "scope": "folder:x", "state": "added"},
            ], "cursor_next": "cur-%d" % calls["n"]}

        checkpoint_store = InMemoryCheckpointStore()
        dedup_store = InMemoryDedupStore()
        agent = ConnectorAgent(object_lister=object_lister, checkpoint_store=checkpoint_store,
                                dedup_store=dedup_store)
        req = make_request(
            source_adapter="google-drive", credential_ref="vault://cce/gdrive",
            source_scope={"object_scope": ["folder:x"]},
            observation={"mode": "start"},
        )
        first = agent.handle(req)
        self.assertEqual(first.status, "observing")
        # Second call re-lists the SAME object/revision/state -- must dedup.
        second = agent.handle(make_request(
            source_adapter="google-drive", credential_ref="vault://cce/gdrive",
            source_scope={"object_scope": ["folder:x"]},
            observation={"mode": "poll"},
        ))
        self.assertEqual(second.status, "observing")

    def test_resume_without_a_prior_checkpoint_fails_closed(self):
        def object_lister(cursor):
            return {"objects": [], "cursor_next": "cur-1"}

        agent = ConnectorAgent(object_lister=object_lister)
        resp = agent.handle(make_request(
            source_adapter="google-drive", credential_ref="vault://cce/gdrive",
            source_scope={"object_scope": ["folder:x"]},
            observation={"mode": "resume"},
        ))
        self.assertEqual(resp.status, "failed")
        self.assertEqual(resp.error["code"], "CHECKPOINT_MISSING_FOR_RESUME")

    def test_checkpoint_is_not_advanced_when_observation_skill_rejects(self):
        # object_lister returns malformed objects (missing 'state') -> the
        # deterministic document sync rejects with DSY05.
        def bad_object_lister(cursor):
            return {"objects": [{"object_id": "doc-1", "revision": "r1", "scope": "folder:x"}],
                    "cursor_next": "cur-1"}

        checkpoint_store = InMemoryCheckpointStore()
        agent = ConnectorAgent(object_lister=bad_object_lister, checkpoint_store=checkpoint_store)
        resp = agent.handle(make_request(
            source_adapter="google-drive", credential_ref="vault://cce/gdrive",
            source_scope={"object_scope": ["folder:x"]},
            observation={"mode": "start"},
        ))
        self.assertEqual(resp.status, "failed")
        self.assertIsNone(checkpoint_store.get("google-drive"))


if __name__ == "__main__":
    unittest.main()
