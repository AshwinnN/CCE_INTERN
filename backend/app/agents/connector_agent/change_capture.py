#!/usr/bin/env python3
"""Deterministic change observation for structured and unstructured sources.

The observers accept injected live-reader callables and perform all sync,
card-building, persistence, and diffing in code. This keeps connector
runtime independent of skill scripts while preserving the same event shape
the ingestion pipeline already consumes.
"""
import copy
import json
from typing import Callable, Dict, List, Optional

from agents.connector_agent.observation import ChangeObserver


class ObserverRejected(Exception):
    def __init__(self, rule):
        self.rule = rule
        super().__init__("observation rejected by rule %s" % rule)


class UnstructuredChangeObserver(ChangeObserver):
    def __init__(self, source_id, adapter, supports_incremental,
                 object_lister: Callable[[Optional[str]], Dict]):
        """object_lister(cursor) -> {"objects": [...], "cursor_next": str}."""
        self._source_id = source_id
        self._adapter = adapter
        self._supports_incremental = supports_incremental
        self._object_lister = object_lister

    def start(self, connection_handle, checkpoint=None):
        return self.poll(connection_handle, checkpoint)

    def poll(self, connection_handle, checkpoint):
        live = self._object_lister(checkpoint if self._supports_incremental else None)
        raw_objects = live.get("objects")
        cursor_next = live.get("cursor_next")
        if not isinstance(raw_objects, list) or cursor_next is None:
            raise ObserverRejected("DSY05")

        by_state = {"added": [], "changed": [], "deleted": []}
        for obj in raw_objects:
            if not isinstance(obj, dict) or not obj.get("object_id") or "state" not in obj:
                raise ObserverRejected("DSY05")
            state = obj["state"]
            if state not in by_state:
                raise ObserverRejected("DSY05")
            by_state[state].append(obj)

        events = []
        for ref in by_state["added"]:
            events.append(self._event(connection_handle, ref, "created", checkpoint, cursor_next))
        for ref in by_state["changed"]:
            events.append(self._event(connection_handle, ref, "updated", checkpoint, cursor_next))
        for ref in by_state["deleted"]:
            events.append(self._event(connection_handle, ref, "deleted", checkpoint, cursor_next))

        return {"events": events, "checkpoint": cursor_next, "truncated": False}

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
                "modified_at": ref.get("modified_at"),
            },
            "change_type": change_type,
            "checkpoint": {"previous_cursor": prev_cursor, "current_cursor": next_cursor},
            "entitlement_state": ref.get("entitlement_state", "unknown"),
        }


class StructuredChangeObserver(ChangeObserver):
    def __init__(self, source_id, adapter, dialect, schema_scope,
                 catalog_lister: Callable[[], List[Dict]],
                 metadata_store_dict: Optional[dict] = None,
                 max_entities: int = 500):
        """catalog_lister() -> [{"schema", "table", "columns": [...], "sample": {...}}]."""
        self._source_id = source_id
        self._adapter = adapter
        self._dialect = dialect
        self._schema_scope = schema_scope
        self._catalog_lister = catalog_lister
        self._store = metadata_store_dict if metadata_store_dict is not None else {}
        self._max_entities = max_entities

    def start(self, connection_handle, checkpoint=None):
        return self.poll(connection_handle, checkpoint)

    def poll(self, connection_handle, checkpoint):
        source_store = self._store.setdefault(self._source_id, {})
        if source_store:
            latest_version = max(int(v) for v in source_store)
            old_card = source_store[str(latest_version)]
            baseline_ref = str(latest_version)
            next_version = latest_version + 1
        else:
            old_card = {"schema": None, "tables": []}
            baseline_ref = None
            next_version = 1

        catalog = self._catalog_lister()
        new_card = _build_schema_card(catalog, self._schema_scope, max_entities=self._max_entities)
        source_store[str(next_version)] = copy.deepcopy(new_card)

        manifest = _diff_schema_cards(old_card, new_card, full_sync=baseline_ref is None)
        checkpoint_out = str(next_version)
        events = []
        for ref in manifest["added"]:
            events.append(self._event(connection_handle, ref, "created", baseline_ref, checkpoint_out))
        for ref in manifest["changed"]:
            events.append(self._event(connection_handle, ref, "updated", baseline_ref, checkpoint_out))
        for ref in manifest["removed"]:
            events.append(self._event(connection_handle, ref, "deleted", baseline_ref, checkpoint_out))

        return {"events": events, "checkpoint": checkpoint_out, "truncated": manifest["truncated"]}

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


def _build_schema_card(catalog: List[Dict], schema_scope: List[str], max_entities: int) -> Dict:
    if not isinstance(catalog, list):
        raise ObserverRejected("SCD05")

    allowed = {s.upper() for s in schema_scope or []}
    tables = []
    for item in catalog:
        if not isinstance(item, dict):
            raise ObserverRejected("SCD05")
        schema = item.get("schema")
        table = item.get("table") or item.get("name")
        columns = item.get("columns")
        if not schema or not table or not isinstance(columns, list):
            raise ObserverRejected("SCD05")
        if allowed and schema.upper() not in allowed:
            continue
        if len(tables) >= max_entities:
            break
        tables.append({
            "schema": schema,
            "name": table,
            "columns": [_normalize_column(c) for c in columns],
            "row_count": item.get("row_count"),
            "sample_row": item.get("sample") or item.get("sample_row"),
        })

    card_schema = schema_scope[0] if schema_scope else (tables[0]["schema"] if tables else None)
    return {"schema": card_schema, "tables": tables}


def _normalize_column(column: Dict) -> Dict:
    if not isinstance(column, dict) or not column.get("name") or not column.get("type"):
        raise ObserverRejected("SCD05")
    return {
        "name": column["name"],
        "type": column["type"],
        "nullable": column.get("nullable", True),
        "sensitive": column.get("sensitive", False),
    }


def _diff_schema_cards(old_card: Dict, new_card: Dict, full_sync: bool = False) -> Dict:
    old_entities = {} if full_sync else _flatten_card(old_card)
    new_entities = _flatten_card(new_card)

    added = [new_entities[k] for k in sorted(new_entities) if k not in old_entities]
    removed = [old_entities[k] for k in sorted(old_entities) if k not in new_entities]
    changed = [
        new_entities[k] for k in sorted(new_entities)
        if k in old_entities and _stable_json(new_entities[k]) != _stable_json(old_entities[k])
    ]
    return {"added": added, "changed": changed, "removed": removed, "truncated": False}


def _flatten_card(card: Dict) -> Dict[str, Dict]:
    entities = {}
    for table in card.get("tables", []) or []:
        schema = table.get("schema") or card.get("schema") or "default"
        table_name = table.get("name")
        if not table_name:
            continue
        table_id = "%s.%s" % (schema, table_name)
        entities[table_id] = {
            "entity_id": table_id,
            "entity_type": "table",
            "schema": schema,
            "table": table_name,
            "columns": [c.get("name") for c in table.get("columns", [])],
            "row_count": table.get("row_count"),
        }
        for column in table.get("columns", []) or []:
            column_name = column.get("name")
            if not column_name:
                continue
            column_id = "%s.%s" % (table_id, column_name)
            entities[column_id] = {
                "entity_id": column_id,
                "entity_type": "column",
                "schema": schema,
                "table": table_name,
                "column": column_name,
                "type": column.get("type"),
                "nullable": column.get("nullable", True),
                "sensitive": column.get("sensitive", False),
            }
    return entities


def _stable_json(value: Dict) -> str:
    return json.dumps(value, sort_keys=True, default=str)
