"""Base governed context asset model."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContextAsset:
    asset_id: str
    asset_type: str
    status: str
    payload: dict = field(default_factory=dict)
