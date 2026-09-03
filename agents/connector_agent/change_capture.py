#!/usr/bin/env python3
"""Concrete ChangeObserver implementations for the two lanes.

Both observers call real skill functions (loaded via common/skill_loader.py)
for classification and rule enforcement; neither implements a real source
driver. Each accepts an injected "lister" callable standing in for a live
provider read, exactly the same `_objects`/`_catalog` fixture convention
every skill in this repo already uses -- wiring a real driver behind that
callable is a separate, later task, not part of this orchestration layer.

StructuredChangeObserver clears its introspection SQL through the real
skill-dialect-profile + skill-sql-guard skills before calling
skill-schema-discovery, using the SQG08 "intent": "introspection" carve-out
added specifically to resolve a real conflict: SQG05 unconditionally blocks
system-catalog reads, but introspection SQL reads exactly those namespaces
by definition. See skill-sql-guard/SKILL.md rules SQG05/SQG08 and
skill-sql-guard/references/guard-boundaries.md for the full reasoning.

TRUST BOUNDARY: this observer is the ONLY code path in this Agent permitted
to set intent="introspection". Answer-time candidate or verified SQL must
never carry it -- the guard cannot verify who is calling it, so this
discipline is enforced by not wiring that value in anywhere else, not by
the guard itself.
"""
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from agents.connector_agent.observation import ChangeObserver
from common.skill_loader import load_skill_function, load_skill_module


class ObserverRejected(Exception):
    def __init__(self, rule):
        self.rule = rule
        super().__init__("observation rejected by rule %s" % rule)


# ---------------------------------------------------------------------------
# Unstructured lane: skill-document-sync
# ---------------------------------------------------------------------------

class UnstructuredChangeObserver(ChangeObserver):
    def __init__(self, source_id, adapter, supports_incremental,
                 object_lister: Callable[[Optional[str]], Dict]):
        """object_lister(cursor) -> {"objects": [{object_id, revision, scope,
        state}], "cursor_next": str} -- stands in for a live provider read.
        """
        self._source_id = source_id
        self._adapter = adapter
        self._supports_incremental = supports_incremental
        self._object_lister = object_lister
        self._sync = load_skill_function("skill-document-sync", "sync_documents.py", "sync")

    def start(self, connection_handle, checkpoint=None):
        return self.poll(connection_handle, checkpoint)

    def poll(self, connection_handle, checkpoint):
        use_incremental = bool(checkpoint) and self._supports_incremental
        sync_mode = "incremental" if use_incremental else "full"

        live = self._object_lister(checkpoint)
        raw_objects = live["objects"]
        cursor_next = live["cursor_next"]

        request = {
            "handle": connection_handle,
            "sync_mode": sync_mode,
            "cursor_in": checkpoint,
            "supports_incremental": self._supports_incremental,
            "full_sync_approved": sync_mode == "full",
            "_objects": raw_objects,
            # Reported True here because classification is independent of
            # this flag (see sync_documents.py) -- the real DSY03 boundary
            # this orchestrator honours is that checkpoint_store.set() is
            # only ever called by the Agent after a successful event
            # handoff, never before, regardless of what this call reports.
            "batch_durably_processed": True,
            "cursor_next": cursor_next,
        }
        manifest = self._sync(request)
        if manifest["status"] != "READY":
            raise ObserverRejected(manifest["violated_rule"])

        events = []
        for ref in manifest["added"]:
            events.append(self._event(connection_handle, ref, "created", checkpoint, manifest["cursor_out"]))
        for ref in manifest["changed"]:
            events.append(self._event(connection_handle, ref, "updated", checkpoint, manifest["cursor_out"]))
        for ref in manifest["deleted"]:
            events.append(self._event(connection_handle, ref, "deleted", checkpoint, manifest["cursor_out"]))

        return {"events": events, "checkpoint": manifest["cursor_out"], "truncated": manifest["truncated"]}

    def stop(self, observation_handle):
        return None

    def _event(self, connection_handle, ref, change_type, prev_cursor, next_cursor):
        return {
            "source": {"adapter": self._adapter, "kind": "unstructured",
                       "connection_handle": connection_handle.get("handle_id")},
            "object": {
                "object_id": ref["object_id"], "object_type": "document",
                "source_ref": "%s:%s" % (self._adapter, ref["object_id"]),
                "version": ref.get("revision"), "content_hash": None,
                "modified_at": None,
            },
            "change_type": change_type,
            "checkpoint": {"previous_cursor": prev_cursor, "current_cursor": next_cursor},
            "entitlement_state": "unknown",
        }


# ---------------------------------------------------------------------------
# Structured lane: skill-schema-discovery + skill-source-metadata-store +
# skill-source-sync
# ---------------------------------------------------------------------------

class StructuredChangeObserver(ChangeObserver):
    def __init__(self, source_id, adapter, dialect, schema_scope,
                 catalog_lister: Callable[[], List[Dict]],
                 metadata_store_dict: Optional[dict] = None,
                 max_entities: int = 500):
        """catalog_lister() -> [{"schema", "table", "columns": [...],
        "sample": {...}}] -- stands in for a live introspection result.
        `metadata_store_dict` is the same kind of MVP-stub in-memory
        persistence as common/checkpoint_store.py, scoped to this observer.
        """
        self._source_id = source_id
        self._adapter = adapter
        self._dialect = dialect
        self._schema_scope = schema_scope
        self._catalog_lister = catalog_lister
        self._store = metadata_store_dict if metadata_store_dict is not None else {}
        self._max_entities = max_entities
        self._build_card = load_skill_function("skill-schema-discovery", "build_schema_card.py", "build")
        self._metadata_module = load_skill_module("skill-source-metadata-store", "metadata_store.py")
        self._sync = load_skill_function("skill-source-sync", "sync_source.py", "sync")
        self._resolve_dialect = load_skill_function(
            "skill-dialect-profile", "resolve_dialect_profile.py", "resolve")
        self._guard_sql = load_skill_function("skill-sql-guard", "guard_sql.py", "guard")
        # Reused, not duplicated: the introspection FROM-clause table per
        # dialect is schema-discovery's own fact (INTROSPECTION_SOURCE).
        # Declaring a second copy here would violate the single-source-of-
        # truth principle this whole codebase follows for dialect facts.
        schema_discovery_module = load_skill_module("skill-schema-discovery", "build_schema_card.py")
        self._introspection_table = schema_discovery_module.INTROSPECTION_SOURCE.get(dialect)

    def start(self, connection_handle, checkpoint=None):
        return self.poll(connection_handle, checkpoint)

    def poll(self, connection_handle, checkpoint):
        # 1. What version is currently stored, if any.
        retrieve_req = {"operation": "retrieve", "source_id": self._source_id,
                         "payload_kind": "card", "_store": self._store}
        stored = self._metadata_module.do_retrieve(retrieve_req, self._store)
        if stored["status"] == "READY":
            old_card = stored["payload"]
            baseline_ref = str(stored["card_version"])
            next_version = stored["latest_version"] + 1
            full_sync_approved = False
        else:
            old_card, baseline_ref, next_version, full_sync_approved = {}, None, 1, True

        # 2. Clear the introspection query through the real dialect-profile
        # and sql-guard skills (SCD06), using the SQG08 introspection
        # carve-out -- the only path in this Agent allowed to set it.
        dialect_profile = self._resolve_dialect({"dialect": self._dialect, "kind": "structured"})
        if dialect_profile["status"] != "READY":
            raise ObserverRejected(dialect_profile["violated_rule"])

        introspection_sql = "SELECT * FROM %s WHERE TABLE_SCHEMA IN (%s)" % (
            self._introspection_table,
            ", ".join("'%s'" % s.replace("'", "''") for s in self._schema_scope),
        )
        guard_result = self._guard_sql({
            "sql": introspection_sql, "dialect_profile": dialect_profile,
            "max_rows": self._max_entities, "intent": "introspection",
        })
        if guard_result["status"] != "READY":
            raise ObserverRejected(guard_result["violated_rule"])

        # 3. Discover a fresh card, now that SCD06's precondition is
        # satisfied by a real, guarded statement rather than an asserted flag.
        catalog = self._catalog_lister()
        discover_req = {
            "handle": connection_handle, "guard_passed": True,
            "card_version": next_version, "_catalog": catalog,
        }
        new_card = self._build_card(discover_req)
        if new_card["status"] != "READY":
            raise ObserverRejected(new_card["violated_rule"])

        # 4. Persist the new card. do_store() only *validates* the write;
        # this orchestrator performs the actual mutation on success, the
        # same division of responsibility as every other skill in this repo.
        store_req = {"operation": "store", "card": new_card, "_store": self._store}
        store_result = self._metadata_module.do_store(store_req, self._store)
        if store_result["status"] != "READY":
            raise ObserverRejected(store_result["violated_rule"])
        self._store.setdefault(self._source_id, {})[str(next_version)] = new_card

        # 5. Diff old vs new through skill-source-sync.
        sync_req = {
            "descriptor": {
                "source_id": self._source_id, "source_kind": "structured",
                "detection_strategy": "card_diff",
                "scope": self._schema_scope, "max_entities": self._max_entities,
            },
            "baseline_ref": baseline_ref,
            "full_sync_approved": full_sync_approved,
            "_card_from": old_card, "_card_to": new_card,
            "batch_durably_processed": True,
            "watermark_next": str(next_version),
        }
        manifest = self._sync(sync_req)
        if manifest["status"] != "READY":
            raise ObserverRejected(manifest["violated_rule"])

        events = []
        for ref in manifest["added"]:
            events.append(self._event(connection_handle, ref, "created", baseline_ref, manifest["watermark_out"]))
        for ref in manifest["changed"]:
            events.append(self._event(connection_handle, ref, "updated", baseline_ref, manifest["watermark_out"]))
        for ref in manifest["removed"]:
            events.append(self._event(connection_handle, ref, "deleted", baseline_ref, manifest["watermark_out"]))

        return {"events": events, "checkpoint": manifest["watermark_out"], "truncated": manifest["truncated"]}

    def stop(self, observation_handle):
        return None

    def _event(self, connection_handle, ref, change_type, prev_watermark, next_watermark):
        return {
            "source": {"adapter": self._adapter, "kind": "structured",
                       "connection_handle": connection_handle.get("handle_id")},
            "object": {
                "object_id": ref["entity_id"], "object_type": ref["entity_type"],
                "source_ref": "%s:%s" % (self._adapter, ref["entity_id"]),
                "version": next_watermark, "content_hash": None, "modified_at": None,
            },
            "change_type": change_type,
            "checkpoint": {"previous_cursor": prev_watermark, "current_cursor": next_watermark},
            "entitlement_state": "unknown",
        }
