#!/usr/bin/env python3
"""Public Connector Agent entrypoint.

ConnectorAgent.handle(request) is the one public call. Everything else in
this package is invoked from here, in the fixed order the design specifies:
registry lookup -> registry validation -> capability check -> credential
resolution -> route -> reshape -> connect -> (optional) observe.
"""
from typing import Callable, List, Optional

from agents.connector_agent import orchestrator, router, errors
from agents.connector_agent.contracts import ConnectorRequest, ConnectorResponse, SkillTraceEntry
from agents.connector_agent.change_capture import (
    UnstructuredChangeObserver, StructuredChangeObserver, ObserverRejected,
)
from common.correlation import new_trace_id, new_event_id
from common.known_adapters import AdapterRegistryProvider, StubAdapterRegistryProvider
from common.checkpoint_store import CheckpointStore, InMemoryCheckpointStore, InMemoryDedupStore

# Ingestion-adjacent skills this Agent must never call, enforced as an
# explicit assertion rather than left as an informal promise -- test #9/#17
# in the design checks exactly this.
FORBIDDEN_SKILLS = {
    "skill-document-content-extraction", "skill-document-chunking",
    "skill-source-normalization", "skill-embedding-generation",
    "skill-fact-extraction", "skill-entity-relationship-extraction",
    "skill-knowledge-graph-upsert", "skill-provenance-capture",
    "skill-candidate-query-generation", "skill-guarded-query-execution",
}


class ConnectorAgent:
    def __init__(self,
                 registry_provider: AdapterRegistryProvider = None,
                 checkpoint_store: CheckpointStore = None,
                 dedup_store: InMemoryDedupStore = None,
                 object_lister: Optional[Callable] = None,
                 catalog_lister: Optional[Callable] = None,
                 structured_metadata_store: Optional[dict] = None,
                 structured_connector_factory: Optional[Callable] = None):
        self._registry_provider = registry_provider or StubAdapterRegistryProvider()
        self._checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self._dedup_store = dedup_store or InMemoryDedupStore()
        # Both listers are test/caller-injected stand-ins for a live driver
        # read -- see change_capture.py's module docstring. Defaults raise,
        # so silently returning no events is never mistaken for "nothing
        # changed" when no real driver has actually been wired.
        self._object_lister = object_lister
        self._catalog_lister = catalog_lister
        self._structured_metadata_store = structured_metadata_store if structured_metadata_store is not None else {}
        # Test/caller-injected stand-in for connectors.factory.ConnectorFactory.create
        # -- see orchestrator.connect_structured()'s docstring. Defaults to
        # the real factory (real, live I/O); tests inject a fake
        # StructuredConnector, the same convention as object_lister/catalog_lister.
        self._structured_connector_factory = structured_connector_factory

    def handle(self, request: ConnectorRequest) -> ConnectorResponse:
        trace_id = new_trace_id()
        skill_trace: List[SkillTraceEntry] = []

        try:
            entry = self._registry_provider.get(request.source_adapter)
            if entry is None:
                raise orchestrator.Blocked(errors.REGISTRY_ADAPTER_UNKNOWN)

            descriptor = orchestrator.validate_registry_entry(entry, trace_id, skill_trace)
            orchestrator.check_requested_capabilities(descriptor, request.requested_capabilities)

            lease = orchestrator.resolve_credential(
                request.credential_ref,
                role=request.source_scope.get("role", "cce_reader"),
                grants=request.source_scope.get("grants", ["SELECT"]),
                ttl_seconds=request.source_scope.get("ttl_seconds", 3600),
                trace_id=trace_id, skill_trace=skill_trace,
            )

            route = router.resolve_route(descriptor["kind"])
            if route == router.STRUCTURED:
                handle = orchestrator.connect_structured(
                    descriptor, request, lease, trace_id, skill_trace,
                    structured_connector_factory=self._structured_connector_factory,
                )
            else:
                handle = orchestrator.connect_unstructured(descriptor, request, trace_id, skill_trace)

            connection = {
                "connection_handle": handle["handle_id"],
                "observation_handle": None,
                "credential_ref_present": bool(request.credential_ref),
                "lease_valid": lease["status"] == "READY",
                "read_only_verified": handle["read_only_verified"],
            }
            status = "connected"
            checkpoint_out = None
            error = None
            events: List[dict] = []

            mode = request.observation.mode
            if mode in ("start", "resume", "poll"):
                events, checkpoint_out, obs_error = self._observe(
                    descriptor, request, handle, route, mode, trace_id, skill_trace,
                )
                connection["observation_handle"] = "obs_%s" % handle["handle_id"]
                if obs_error is not None:
                    status = "failed"
                    error = obs_error.to_dict()
                    events = []
                else:
                    status = "observing"

            return ConnectorResponse(
                trace_id=trace_id, request_id=request.request_id, status=status,
                source={"adapter": descriptor["adapter"], "kind": descriptor["kind"],
                        "dialect": descriptor.get("dialect")},
                connection=connection,
                capabilities=[k for k, v in (descriptor.get("capabilities") or {}).items() if v],
                skill_trace=skill_trace, checkpoint=checkpoint_out, error=error,
                change_events=events,
            )

        except orchestrator.Blocked as exc:
            return ConnectorResponse(
                trace_id=trace_id, request_id=request.request_id, status="blocked",
                source={"adapter": request.source_adapter, "kind": None, "dialect": None},
                connection={"connection_handle": None, "observation_handle": None,
                            "credential_ref_present": bool(request.credential_ref),
                            "lease_valid": False, "read_only_verified": None},
                capabilities=[], skill_trace=skill_trace, checkpoint=None,
                error=exc.error.to_dict(),
            )
        except orchestrator.Failed as exc:
            return ConnectorResponse(
                trace_id=trace_id, request_id=request.request_id, status="failed",
                source={"adapter": request.source_adapter, "kind": None, "dialect": None},
                connection={"connection_handle": None, "observation_handle": None,
                            "credential_ref_present": bool(request.credential_ref),
                            "lease_valid": False, "read_only_verified": None},
                capabilities=[], skill_trace=skill_trace, checkpoint=None,
                error=exc.error.to_dict(),
            )

    def _observe(self, descriptor, request, handle, route, mode, trace_id, skill_trace):
        source_id = request.source_scope.get("source_id", request.source_adapter)

        if mode == "resume":
            existing = self._checkpoint_store.get(source_id)
            if existing is None:
                return [], None, errors.make_error(errors.CHECKPOINT_MISSING_FOR_RESUME)
            checkpoint_in = existing
        elif mode == "poll":
            checkpoint_in = self._checkpoint_store.get(source_id)
        else:  # start
            checkpoint_in = request.observation.checkpoint

        try:
            if route == router.STRUCTURED:
                if self._catalog_lister is None:
                    raise ObserverRejected("NO_CATALOG_LISTER_CONFIGURED")
                observer = StructuredChangeObserver(
                    source_id=source_id, adapter=descriptor["adapter"],
                    dialect=descriptor.get("dialect"),
                    schema_scope=request.source_scope.get("schema_scope", []),
                    catalog_lister=self._catalog_lister,
                    metadata_store_dict=self._structured_metadata_store,
                )
                skill_names = ("skill-dialect-profile", "skill-sql-guard", "skill-schema-discovery",
                               "skill-source-metadata-store", "skill-source-sync")
            else:
                if self._object_lister is None:
                    raise ObserverRejected("NO_OBJECT_LISTER_CONFIGURED")
                observer = UnstructuredChangeObserver(
                    source_id=source_id, adapter=descriptor["adapter"],
                    supports_incremental=descriptor.get("capabilities", {}).get("incremental_sync", False),
                    object_lister=self._object_lister,
                )
                skill_names = ("skill-document-sync",)

            result = observer.start(handle, checkpoint_in) if mode == "start" else observer.poll(handle, checkpoint_in)
            for name in skill_names:
                skill_trace.append(SkillTraceEntry(skill=name, status="success", trace_id=trace_id))

        except ObserverRejected:
            return [], self._checkpoint_store.get(source_id), errors.make_error(errors.OBSERVATION_SKILL_REJECTED)

        # Deduplicate, then hand off, then -- only on successful handoff --
        # advance the persisted checkpoint. This ordering is the actual DSY03
        # /SSY03 guarantee this orchestrator provides.
        handed_off = []
        for raw_event in result["events"]:
            event_id = new_event_id()
            idem_key = "|".join([
                request.tenant_id, raw_event["source"]["adapter"],
                raw_event["object"]["object_id"], str(raw_event["object"]["version"]),
                raw_event["change_type"],
            ])
            if self._dedup_store.already_handled(idem_key):
                continue
            event = dict(raw_event)
            event["event_id"] = event_id
            event["trace_id"] = trace_id
            event["tenant_id"] = request.tenant_id
            event["event_status"] = "queued"
            event["next_stage"] = "ingest_and_ground"
            event["error"] = None
            handed_off.append(event)
            self._dedup_store.mark_handled(idem_key)

        self._checkpoint_store.set(source_id, result["checkpoint"])
        return handed_off, result["checkpoint"], None
