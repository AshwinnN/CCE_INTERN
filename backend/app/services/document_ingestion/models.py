from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DocumentChunk:
    chunk_id: str
    chunk_index: int
    total_chunks: int
    content: str
    metadata: dict[str, Any]
    content_size_bytes: int
    metadata_size_bytes: int
    payload_size_bytes: int


@dataclass
class DocumentIngestionResult:
    document_id: str
    markdown_size_bytes: int
    total_chunks: int
    chunks: list[DocumentChunk]
    stored_results: list[Any]