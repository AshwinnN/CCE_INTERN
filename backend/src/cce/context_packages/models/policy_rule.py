"""Policy rule model."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    expression: str
