"""Governance transition rules."""

VALID_TRANSITIONS = {
    "proposed": {"review", "rejected"},
    "review": {"approved", "rejected"},
    "approved": {"proposed"},
    "rejected": {"proposed"},
}


def can_transition(current: str, target: str) -> bool:
    return target in VALID_TRANSITIONS.get(current, set())
