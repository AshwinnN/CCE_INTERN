#!/usr/bin/env python3
"""Deterministic context validation helper."""


def validate(context: dict) -> dict:
    return {"status": "OK", "errors": [] if isinstance(context, dict) else ["context must be a dict"]}
