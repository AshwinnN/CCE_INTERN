#!/usr/bin/env python3
"""MVP STUB -- replace with persistent checkpoint storage.

No skill in this repo persists a generic opaque cursor/checkpoint across
observation cycles. skill-source-metadata-store only stores versioned schema
cards (keyed by source_id + card_version, MDS01) -- a different, narrower
contract than "remember the last cursor/watermark for this source_id",
and repurposing it for that would be a contract misuse, not a reuse.

This is explicitly Agent-owned state, not a Skill: it has no Core Rules, no
SKILL.md, no rule IDs, because it isn't validating anything -- it's just
remembering a value between calls, the same way any orchestrator needs
somewhere to keep its own run state.
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
