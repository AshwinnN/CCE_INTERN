#!/usr/bin/env python3
"""Checkpoint and dedup storage for source observation and ingestion.

Observation cursors are keyed by source. Ingestion outcomes are keyed by
``(source_id, object_id)`` so partially processed changes can be resumed.
Production deployments should replace these stores with PostgreSQL-backed
implementations behind the same interfaces.
"""

import json
import os
import re
from typing import Optional


class CheckpointStore:
    """Interface a real persistent store should implement to replace this
    stub without any change to Agent orchestration code."""

    def get(self, source_id):
        raise NotImplementedError

    def set(self, source_id, checkpoint):
        raise NotImplementedError


class InMemoryCheckpointStore(CheckpointStore):
    """MVP STUB -- replace with persistent checkpoint storage."""

    def __init__(self):
        self._data = {}

    def get(self, source_id):
        return self._data.get(source_id)

    def set(self, source_id, checkpoint):
        self._data[source_id] = checkpoint


class InMemoryDedupStore:
    """Tracks idempotency keys already handed off, so a duplicate change
    event (same tenant+adapter+object+version+change_type) never produces a
    duplicate handoff. Same MVP-stub status as CheckpointStore -- a real
    deployment needs this to survive a process restart, this one does not.
    """

    def __init__(self):
        self._seen = set()

    def already_handled(self, idempotency_key):
        return idempotency_key in self._seen

    def mark_handled(self, idempotency_key):
        self._seen.add(idempotency_key)


def _safe_key_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


class IngestionCheckpointStore:
    def __init__(self, store_path: Optional[str] = None):
        self.store_path = store_path or os.environ.get(
            "CCE_CHECKPOINT_STORE_PATH", ".ingestion_checkpoints")
        os.makedirs(self.store_path, exist_ok=True)

    def _checkpoint_id(self, source_id: str, object_id: str) -> str:
        return "%s__%s" % (_safe_key_part(source_id), _safe_key_part(object_id))

    def _path(self, checkpoint_id: str) -> str:
        return os.path.join(self.store_path, "%s.json" % checkpoint_id)

    def save(self, source_id: str, object_id: str, state: dict) -> str:
        checkpoint_id = self._checkpoint_id(source_id, object_id)
        with open(self._path(checkpoint_id), "w") as f:
            json.dump(state, f, indent=2, default=str)
        return checkpoint_id

    def load(self, source_id: str, object_id: str) -> Optional[dict]:
        checkpoint_id = self._checkpoint_id(source_id, object_id)
        path = self._path(checkpoint_id)
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            return json.load(f)

    def mark_complete(self, source_id: str, object_id: str, revision: str) -> str:
        return self.save(source_id, object_id, {"status": "complete", "revision": revision})


_default_ingestion_store: Optional[IngestionCheckpointStore] = None


def get_ingestion_checkpoint_store() -> IngestionCheckpointStore:
    global _default_ingestion_store
    if _default_ingestion_store is None:
        _default_ingestion_store = IngestionCheckpointStore()
    return _default_ingestion_store
