"""Runtime state shared across query execution steps."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeState:
    question: str
    trace_id: str | None = None
    values: dict[str, Any] = field(default_factory=dict)
