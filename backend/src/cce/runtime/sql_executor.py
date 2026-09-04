"""Read-only SQL execution boundary."""

from cce.core.errors import NotImplementedCCEError


def execute_read_only(*args, **kwargs):
    raise NotImplementedCCEError("read-only SQL execution is not implemented yet")
