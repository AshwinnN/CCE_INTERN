from __future__ import annotations

from typing import Any

from agenticplane.types import MemoryType, SearchOptions

from integrations.agenticplane.client import get_client


class AgenticPlaneService:

    async def store_memory(
        self,
        *,
        agent_id: str,
        content: str,
        memory_type: MemoryType,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> Any:
        client = await get_client()

        return await client.memory.store(
            agent_id=agent_id,
            content=content,
            memory_type=memory_type,
            metadata=metadata or {},
            tags=tags or [],
        )

    async def store_memories(
        self,
        *,
        items: list[dict[str, Any]],
    ) -> Any:
        client = await get_client()

        return await client.memory.store_batch(items)

    async def search_memory(
        self,
        *,
        agent_id: str,
        query: str,
        options: SearchOptions,
    ) -> Any:
        client = await get_client()

        return await client.memory.search(
            agent_id=agent_id,
            query=query,
            options=options,
        )

    async def extract_graph(
        self,
        *,
        agent_id: str,
        content: str,
    ) -> Any:
        client = await get_client()

        return await client.graph.extract_and_store(
            content,
            agent_id=agent_id,
        )   

    async def health_check(self) -> bool:
        client = await get_client()
        return await client.health_check()

    async def ready_check(self) -> bool:
        client = await get_client()
        return await client.ready_check()

    async def health(self) -> Any:
        client = await get_client()
        return await client.health()


agenticplane_service = AgenticPlaneService()