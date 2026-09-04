"""Role helpers for backend authorization."""

from cce.core.enums import ActorRole


def has_role(actor, role: ActorRole) -> bool:
    return role.value in getattr(actor, "roles", [])
