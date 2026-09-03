#!/usr/bin/env python3
"""Durable, file-based checkpoint store for the ingestion workflow's
checkpoint node -- resumable per-(source_id, object_id) processing state.

Distinct in scope from common/checkpoint_store.py: that module is the
Connector Agent's per-source_id observation *cursor* (in-memory MVP stub,
owned by agents/connector_agent/agent.py). This module is the ingestion
workflow's per-(source_id, object_id) *processing outcome* -- did this
specific change event finish, and if not, why -- and is file-backed from
the start because resuming a partially-processed document across process
restarts is the actual point of it (see ingestion_summary.md's
checkpoint_manager.py spec). Swap the backing store, not the workflow, when
a real DB/Redis-backed implementation replaces it -- same interface
discipline as every other MVP-stub store in this repo.
"""
import json
import os
import re
from typing import Optional


def _safe_key_part(value: str) -> str:
    """Both source_id and object_id can contain characters that aren't safe
    in a filename (e.g. object_id is often a path like 'folder/doc.pdf').
    Escape rather than reject -- a checkpoint key must always be storable."""
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
        """Save checkpoint state, return the checkpoint_id it was saved under."""
        checkpoint_id = self._checkpoint_id(source_id, object_id)
        with open(self._path(checkpoint_id), "w") as f:
            json.dump(state, f, indent=2, default=str)
        return checkpoint_id

    def load(self, source_id: str, object_id: str) -> Optional[dict]:
        """Load a prior checkpoint, or None if none exists."""
        checkpoint_id = self._checkpoint_id(source_id, object_id)
        path = self._path(checkpoint_id)
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            return json.load(f)

    def mark_complete(self, source_id: str, object_id: str, revision: str) -> str:
        """Mark this (source_id, object_id) as successfully processed at
        `revision`, so a later resume attempt can see it's already done."""
        return self.save(source_id, object_id, {"status": "complete", "revision": revision})


# Global instance, matching common/checkpoint_store.py's module-level default
# -- callers that need isolation (tests) should construct their own
# IngestionCheckpointStore(store_path=...) instead of using this one.
_default_store: Optional[IngestionCheckpointStore] = None


def get_ingestion_checkpoint_store() -> IngestionCheckpointStore:
    global _default_store
    if _default_store is None:
        _default_store = IngestionCheckpointStore()
    return _default_store
