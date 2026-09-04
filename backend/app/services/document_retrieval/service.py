from __future__ import annotations

from typing import Any

from agenticplane.types import SearchOptions

from services.agenticplane.service import (
    agenticplane_service,
)


class DocumentRetrievalService:

    async def retrieve(
        self,
        *,
        agent_id: str,
        query: str,
        options: SearchOptions,
    ) -> Any:
        """
        Retrieve document knowledge from AgenticPlane.

        This service is intentionally generic so that any
        CCE service can invoke it.
        """

        if not agent_id:
            raise ValueError(
                "agent_id is required"
            )

        if not query:
            raise ValueError(
                "query is required"
            )

        return await (
            agenticplane_service.search_memory(
                agent_id=agent_id,
                query=query,
                options=options,
            )
        )


document_retrieval_service = (
    DocumentRetrievalService()
)