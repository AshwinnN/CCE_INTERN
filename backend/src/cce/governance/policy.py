"""Approved-only serving policy boundary."""


def require_approved(status: str) -> None:
    if status != "approved":
        raise PermissionError("context asset is not approved")
