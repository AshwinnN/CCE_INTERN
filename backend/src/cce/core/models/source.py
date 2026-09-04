"""Source identity and configuration models."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Source:
    source_id: str
    adapter: str
    kind: str
    config: dict = field(default_factory=dict)
