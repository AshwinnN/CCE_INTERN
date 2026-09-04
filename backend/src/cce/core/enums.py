"""Shared CCE enums."""

from enum import StrEnum


class ActorRole(StrEnum):
    ADMIN = "ADMIN"
    STEWARD = "STEWARD"
    QUERY_CONSUMER = "QUERY_CONSUMER"


class SourceKind(StrEnum):
    STRUCTURED = "structured"
    UNSTRUCTURED = "unstructured"


class LifecycleStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
