from __future__ import annotations

import asyncio
from typing import Any

from services.agenticplane.service import agenticplane_service

from .chunker import chunk_markdown
from .content_to_markdown import convert_content_to_markdown
from .models import DocumentIngestionResult


MAX_PARALLEL_CHUNKS = 10


class DocumentIngestionService:

    async def ingest_document(
        self,
        *,
        metadata: dict[str, Any],
        content: dict[str, Any],
        agent_id: str,
        memory_type: Any,
        tags: list[str] | None = None,
    ) -> DocumentIngestionResult:

        document_id = metadata.get("document_id")

        if not document_id:
            raise ValueError(
                "metadata.document_id is required"
            )

        if not content:
            raise ValueError(
                "content is required"
            )

        # --------------------------------------------------
        # 1. Convert structured content to Markdown
        # --------------------------------------------------

        markdown = convert_content_to_markdown(content)

        markdown_size_bytes = len(
            markdown.encode("utf-8")
        )

        # --------------------------------------------------
        # 2. Markdown chunks
        # --------------------------------------------------

        chunks = chunk_markdown(
            markdown=markdown,
            metadata=metadata,
            document_id=document_id,
        )

        # --------------------------------------------------
        # 3. Send chunks to AgenticPlane in parallel
        # --------------------------------------------------

        semaphore = asyncio.Semaphore(
            MAX_PARALLEL_CHUNKS
        )

        async def store_chunk(chunk):
            async with semaphore:

                return await agenticplane_service.store_memory(
                    agent_id=agent_id,
                    content=chunk.content,
                    memory_type=memory_type,
                    metadata=chunk.metadata,
                    tags=tags,
                )

        stored_results = await asyncio.gather(
            *[
                store_chunk(chunk)
                for chunk in chunks
            ]
        )

        return DocumentIngestionResult(
            document_id=document_id,
            total_chunks=len(chunks),
            markdown_size_bytes=markdown_size_bytes,
            chunks=chunks,
            stored_results=stored_results,
        )


document_ingestion_service = DocumentIngestionService()