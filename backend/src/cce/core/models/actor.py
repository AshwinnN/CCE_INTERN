"""Caller identity and role information."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Actor:
    actor_id: str
    roles: list[str] = field(default_factory=list)
