"""Approved ambiguity model."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Ambiguity:
    term: str
    interpretation: str
