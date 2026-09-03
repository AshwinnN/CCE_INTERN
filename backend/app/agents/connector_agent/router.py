#!/usr/bin/env python3
"""Routes on registry `kind` only. No adapter/vendor name ever appears in a
conditional here -- that is the one hard rule this whole design keeps
repeating across every skill, and the Agent is not exempt from it.
"""

STRUCTURED = "structured"
UNSTRUCTURED = "unstructured"


def resolve_route(kind: str) -> str:
    if kind == "structured":
        return STRUCTURED
    if kind == "unstructured":
        return UNSTRUCTURED
    raise ValueError("unrecognized kind for routing: %r" % kind)
