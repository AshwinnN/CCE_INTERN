"""Verified SQL model."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VerifiedSQL:
    sql_id: str
    sql: str
