"""Package identity and version metadata."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Package:
    package_id: str
    name: str
    active_version: str | None = None
