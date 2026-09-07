"""Shared normalized-payload chunking for all index backends."""

from __future__ import annotations

from collections.abc import Iterable


def payload_chunks(payload: dict) -> Iterable[dict]:
    """Yield block and table-cell chunks without changing ingestion semantics."""
    for block in payload.get("blocks", []):
        text = block.get("text")
        if text:
            yield {
                "chunk_text": text,
                "metadata": {"block_id": block.get("id"), "type": block.get("type")},
            }
        for cell in block.get("cells") or []:
            if isinstance(cell, dict) and cell.get("text"):
                yield {
                    "chunk_text": cell["text"],
                    "metadata": {
                        "block_id": block.get("id"),
                        "type": block.get("type"),
                        "row": cell.get("row"),
                        "col": cell.get("col"),
                    },
                }
