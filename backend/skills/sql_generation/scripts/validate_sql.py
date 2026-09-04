#!/usr/bin/env python3
"""Deterministic pre-check before runtime SQL guard."""


def validate(sql: str) -> dict:
    ok = sql.strip().lower().startswith("select")
    return {"status": "OK" if ok else "REJECTED", "violated_rule": None if ok else "SELECT_ONLY"}
