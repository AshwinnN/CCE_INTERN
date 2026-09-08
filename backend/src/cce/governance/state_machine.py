"""A resolved proposal is immutable. Corrections are new proposals."""

VALID_TRANSITIONS = {"PROPOSED": {"APPROVED", "REJECTED"}}


def can_transition(current: str, target: str) -> bool:
    return target in VALID_TRANSITIONS.get(current, set())
