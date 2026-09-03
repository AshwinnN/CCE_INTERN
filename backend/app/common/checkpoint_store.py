#!/usr/bin/env python3
"""MVP checkpoint and dedup storage.

This is Agent-owned state: it remembers opaque observation cursors and
idempotency keys between calls. Production deployments should replace the
in-memory classes with durable implementations behind the same interfaces.
"""


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
