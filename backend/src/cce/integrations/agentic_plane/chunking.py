"""Content-element chunking; offsets refer to original element text."""
import json
import re
from uuid import NAMESPACE_URL, uuid5
import tiktoken


def _spans(text, target, overlap, encoding):
    start = 0
    while start < len(text):
        lo, hi, end = start + 1, len(text), start + 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if len(encoding.encode(text[start:mid], disallowed_special=())) <= target:
                end, lo = mid, mid + 1
            else:
                hi = mid - 1
        if end < len(text):
            for pattern in (r"\n\s*\n", r"\n", r"[.!?]\s+", r"\s+"):
                boundaries = list(re.finditer(pattern, text[start:end]))
                if boundaries and boundaries[-1].end() > (end-start)//2:
                    end = start + boundaries[-1].end()
                    break
        yield start, end
        if end == len(text):
            break
        next_start = end
        if overlap:
            while next_start > start + 1 and len(encoding.encode(text[next_start-1:end], disallowed_special=())) <= overlap:
                next_start -= 1
        start = max(start + 1, next_start)


def _table_text(block):
    rows = {}
    for cell in block.get("cells") or []:
        rows.setdefault(cell.get("row", 0), {})[cell.get("col", 0)] = str(cell.get("text", "")).replace("|", "\\|").replace("\n", "<br>")
    if not rows:
        return block.get("text") or block.get("caption") or ""
    width = max(max(row) for row in rows.values()) + 1
    lines = ["| " + " | ".join(row.get(c, "") for c in range(width)) + " |" for _, row in sorted(rows.items())]
    lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
    return "\n".join(filter(None, [block.get("text") or block.get("caption"), *lines]))


def payload_chunks(payload: dict, *, target_tokens=1000, overlap_tokens=125):
    if target_tokens < 1 or not 0 <= overlap_tokens < target_tokens:
        raise ValueError("Require target_tokens > overlap_tokens >= 0")
    encoding = tiktoken.get_encoding("cl100k_base")
    base = {**payload.get("metadata", {})}
    for key in ("workspace_id", "source_id", "document_id", "mime_type", "source_uri"):
        if payload.get(key) is not None:
            base.setdefault(key, payload[key])
    base.setdefault("document_version", payload.get("revision", ""))
    base.setdefault("source_uri", payload.get("source_ref", ""))
    index = 0

    def walk(blocks, ancestry):
        nonlocal index
        headings = list(ancestry)
        for ordinal, block in enumerate(blocks):
            kind = block.get("type", "text")
            meta = {**base, **block.get("metadata", {})}
            if kind in ("heading", "section"):
                level = int(meta.get("level") or meta.get("heading_level") or 1)
                headings = headings[:max(0, level-1)] + [block.get("text", "")]
            meta.setdefault("section_path", list(headings))
            for key in ("page_number", "bbox", "confidence", "parent_id", "char_start", "char_end"):
                if block.get(key) is not None:
                    meta[key] = block[key]
            meta["element_id"] = meta["block_id"] = block.get("id", str(ordinal))
            meta["type"] = kind
            table = kind in ("table", "spreadsheet") or bool(block.get("cells"))
            meta["record_type"] = "structured_evidence" if table else "document_chunk"
            text = _table_text(block) if table else block.get("text", "")
            for start, end in _spans(text, target_tokens, 0 if table else overlap_tokens, encoding):
                coordinates = {**meta, "char_start": meta.get("char_start", 0) + start,
                               "char_end": meta.get("char_start", 0) + end, "chunk_index": index}
                identity = [coordinates.get(k) for k in ("workspace_id", "source_id", "document_id", "document_version", "element_id", "char_start", "char_end")]
                coordinates["chunk_id"] = str(uuid5(NAMESPACE_URL, json.dumps(identity, default=str) + text[start:end]))
                yield {"chunk_text": text[start:end], "metadata": coordinates}
                index += 1
            yield from walk(block.get("children", []) + block.get("tables", []), headings)

    yield from walk(payload.get("blocks", payload.get("elements", [])), [])
