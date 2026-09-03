from typing import Any, Dict

from integrations.agenticplane import AgenticPlaneMemory


class MemoryService:
    """Application-facing service that delegates memory operations to CCE's SDK boundary."""

    def __init__(self, memory: AgenticPlaneMemory | None = None):
        self.memory = memory or AgenticPlaneMemory()

    def store(self, request: Dict[str, Any]):
        return self.memory.store(**request)

    def store_batch(self, request: Dict[str, Any]):
        return self.memory.store_batch(**request)

    def search(self, request: Dict[str, Any]):
        return self.memory.search(**request)
