#!/usr/bin/env python3
"""Export CanonicalDocument unstructured blocks as nested content JSON."""
from typing import Any, Dict, List, Optional


def to_structured_content_json(document: Dict[str, Any],
                               max_content_items: Optional[int] = None) -> Dict[str, Any]:
    metadata = document.get("metadata", {})
    elements = document.get("elements", [])
    title = _document_title(metadata, elements)
    sections = []
    current_section = None
    emitted = 0

    for element in elements:
        item = _element_to_content_item(element)
        if item is None:
            continue
        if max_content_items is not None and emitted >= max_content_items:
            break

        if item["type"] == "heading":
            current_section = {
                "type": "section",
                "title": item["text"],
                "page_number": item.get("page_number"),
                "content": [item],
            }
            sections.append(current_section)
        else:
            if current_section is None:
                current_section = {
                    "type": "section",
                    "title": title,
                    "page_number": item.get("page_number"),
                    "content": [],
                }
                sections.append(current_section)
            if item["type"] == "list" and current_section["content"]:
                previous = current_section["content"][-1]
                if previous.get("type") == "list" and previous.get("page_number") == item.get("page_number"):
                    previous.setdefault("items", []).extend(item.get("items", []))
                    emitted += 1
                    continue
            current_section["content"].append(item)
        emitted += 1

    return {
        "metadata": metadata,
        "content": {
            "document_title": title,
            "sections": sections,
        },
    }


def _document_title(metadata: Dict[str, Any], elements: List[Dict[str, Any]]) -> str:
    for element in elements:
        if element.get("type") == "heading" and element.get("text"):
            return element["text"]
    return metadata.get("original_filename") or metadata.get("document_id") or "Untitled document"


def _element_to_content_item(element: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    element_type = element.get("type")
    if element_type == "list_item":
        return {
            "type": "list",
            "page_number": element.get("page_number"),
            "items": [_strip_list_marker(element.get("text", ""))],
        }
    if element_type in ("heading", "paragraph", "text"):
        content_type = "paragraph" if element_type == "text" else element_type
        return {
            "type": content_type,
            "text": element.get("text", ""),
            "page_number": element.get("page_number"),
        }
    if element_type == "table":
        return {
            "type": "table",
            "caption": element.get("caption"),
            "page_number": element.get("page_number"),
            "rows": _table_rows(element.get("cells", [])),
        }
    if element_type == "image":
        return {
            "type": "image",
            "page_number": element.get("page_number"),
            "caption": element.get("caption"),
            "image_reference": element.get("image_reference"),
        }
    return None


def _strip_list_marker(text: str) -> str:
    import re

    return re.sub(r"^(\u2022|-|\*|\d+[\.)])\s+", "", text).strip()


def _table_rows(cells: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: Dict[int, Dict[int, str]] = {}
    for cell in cells:
        rows.setdefault(int(cell.get("row", 0)), {})[int(cell.get("col", 0))] = cell.get("text", "")
    if not rows:
        return []

    ordered_row_ids = sorted(rows)
    headers = rows.get(ordered_row_ids[0], {})
    result = []
    for row_id in ordered_row_ids[1:]:
        row = {}
        for col_id, value in sorted(rows[row_id].items()):
            key = headers.get(col_id) or "column_%d" % col_id
            row[key] = value
        result.append(row)
    return result
