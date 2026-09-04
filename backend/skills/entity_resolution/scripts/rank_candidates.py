#!/usr/bin/env python3
"""Deterministic candidate ranking helper."""


def rank(candidates):
    return sorted(candidates, key=lambda item: item.get("score", 0), reverse=True)
