"""Candidate SQL generation boundary."""

from cce.core.errors import NotImplementedCCEError


def generate_sql(*args, **kwargs):
    raise NotImplementedCCEError("candidate SQL generation is not implemented yet")
