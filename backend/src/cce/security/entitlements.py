"""Entitlement enforcement boundary."""


def assert_entitled(allowed: bool) -> None:
    if not allowed:
        raise PermissionError("actor is not entitled to this resource")
