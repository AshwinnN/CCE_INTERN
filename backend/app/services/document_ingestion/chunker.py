from __future__ import annotations

import json
from typing import Any

from .models import DocumentChunk


MAX_PAYLOAD_SIZE_BYTES = 256 * 1024

# We intentionally target below the absolute AgenticPlane limit.
TARGET_PAYLOAD_SIZE_BYTES = 200 * 1024

PAYLOAD_SAFETY_MARGIN_BYTES = 4 * 1024


def _json_size_bytes(value: Any) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _build_metadata(
    *,
    base_metadata: dict[str, Any],
    document_id: str,
    chunk_index: int,
    total_chunks: int,
    content_size_bytes: int,
) -> dict[str, Any]:
    return {
        **base_metadata,
        "document_id": document_id,
        "content_format": "markdown",
        "chunk_id": f"{document_id}:chunk:{chunk_index}",
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        "content_size_bytes": content_size_bytes,
    }


def _payload_size_bytes(
    *,
    content: str,
    metadata: dict[str, Any],
) -> int:
    payload = {
        "content": content,
        "metadata": metadata,
    }

    return _json_size_bytes(payload)


def _split_markdown_blocks(markdown: str) -> list[str]:
    """
    Split Markdown into logical blocks using blank lines.
    """

    blocks = []
    current: list[str] = []

    for line in markdown.splitlines():
        if line.strip() == "":
            if current:
                blocks.append("\n".join(current).strip())
                current = []
        else:
            current.append(line)

    if current:
        blocks.append("\n".join(current).strip())

    return [block for block in blocks if block]


def _build_candidate(
    blocks: list[str],
    start_index: int,
    available_size: int,
) -> tuple[str, int]:
    selected: list[str] = []
    current_size = 0
    index = start_index

    while index < len(blocks):
        block = blocks[index]

        separator_size = 2 if selected else 0

        block_size = len(block.encode("utf-8"))

        if current_size + separator_size + block_size > available_size:
            break

        selected.append(block)
        current_size += separator_size + block_size
        index += 1

    return "\n\n".join(selected), index


def _split_large_text(text: str, max_bytes: int) -> list[str]:
    """
    Safely split a large UTF-8 string without cutting in the middle
    of a UTF-8 character.
    """

    if len(text.encode("utf-8")) <= max_bytes:
        return [text]

    pieces: list[str] = []
    current: list[str] = []
    current_size = 0

    for word in text.split(" "):
        word_size = len(word.encode("utf-8"))
        separator_size = 1 if current else 0

        if current and current_size + separator_size + word_size > max_bytes:
            pieces.append(" ".join(current))
            current = []
            current_size = 0
            separator_size = 0

        current.append(word)
        current_size += separator_size + word_size

    if current:
        pieces.append(" ".join(current))

    return pieces


def chunk_markdown(
    *,
    markdown: str,
    metadata: dict[str, Any],
    document_id: str,
) -> list[DocumentChunk]:
    """
    Split Markdown so that the complete AgenticPlane payload,
    including metadata, stays below the configured limit.
    """

    if not markdown.strip():
        raise ValueError("markdown content is empty")

    blocks = _split_markdown_blocks(markdown)

    # First pass creates content chunks.
    content_chunks: list[str] = []

    current_blocks: list[str] = []

    for block in blocks:
        candidate_blocks = current_blocks + [block]
        candidate_content = "\n\n".join(candidate_blocks)

        provisional_metadata = {
            **metadata,
            "document_id": document_id,
            "content_format": "markdown",
            "chunk_id": f"{document_id}:chunk:0",
            "chunk_index": 0,
            "total_chunks": 1,
            "content_size_bytes": len(
                candidate_content.encode("utf-8")
            ),
        }

        payload_size = _payload_size_bytes(
            content=candidate_content,
            metadata=provisional_metadata,
        )

        if (
            payload_size
            <= TARGET_PAYLOAD_SIZE_BYTES
            and payload_size
            <= MAX_PAYLOAD_SIZE_BYTES - PAYLOAD_SAFETY_MARGIN_BYTES
        ):
            current_blocks = candidate_blocks
            continue

        if current_blocks:
            content_chunks.append("\n\n".join(current_blocks))
            current_blocks = [block]
        else:
            # Single block itself is too large.
            content_chunks.extend(
                _split_large_text(
                    block,
                    TARGET_PAYLOAD_SIZE_BYTES,
                )
            )
            current_blocks = []

    if current_blocks:
        content_chunks.append("\n\n".join(current_blocks))

    total_chunks = len(content_chunks)

    chunks: list[DocumentChunk] = []

    for index, chunk_content in enumerate(content_chunks):
        content_size_bytes = len(chunk_content.encode("utf-8"))

        chunk_metadata = _build_metadata(
            base_metadata=metadata,
            document_id=document_id,
            chunk_index=index,
            total_chunks=total_chunks,
            content_size_bytes=content_size_bytes,
        )

        payload_size = _payload_size_bytes(
            content=chunk_content,
            metadata=chunk_metadata,
        )

        metadata_size = _json_size_bytes(
            chunk_metadata
        )

        if payload_size > MAX_PAYLOAD_SIZE_BYTES:
            raise ValueError(
                f"Chunk {index} exceeds AgenticPlane limit: "
                f"{payload_size} bytes > "
                f"{MAX_PAYLOAD_SIZE_BYTES} bytes"
            )       

        chunks.append(
            DocumentChunk(
                chunk_id=chunk_metadata["chunk_id"],
                chunk_index=index,
                total_chunks=total_chunks,
                content=chunk_content,
                metadata=chunk_metadata,
                content_size_bytes=content_size_bytes,      
                metadata_size_bytes=metadata_size,         
                payload_size_bytes=payload_size,
            )
        )

    return chunks