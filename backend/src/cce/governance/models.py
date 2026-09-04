"""Governance lifecycle models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    status: str
