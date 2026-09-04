from __future__ import annotations

from typing import Any


def convert_content_to_markdown(content: Any) -> str:
    """
    Convert structured document content into Markdown.

    Supported structures include:
    - document_title
    - sections
    - headings
    - paragraphs
    - lists
    - tables
    - images
    """

    lines: list[str] = []

    if not isinstance(content, dict):
        raise ValueError("content must be a dictionary")

    document_title = content.get("document_title")

    if document_title:
        lines.append(f"# {document_title}")
        lines.append("")

    sections = content.get("sections", [])

    if isinstance(sections, list):
        for section in sections:
            _render_section(section, lines)

    return "\n".join(lines).strip() + "\n"


def _render_section(section: Any, lines: list[str]) -> None:
    if not isinstance(section, dict):
        return

    title = section.get("title") or section.get("heading")

    if title:
        lines.append(f"## {title}")
        lines.append("")

    section_content = section.get("content", [])

    if isinstance(section_content, list):
        for item in section_content:
            _render_content_item(item, lines)


def _render_content_item(item: Any, lines: list[str]) -> None:
    if not isinstance(item, dict):
        if item is not None:
            lines.append(str(item))
            lines.append("")
        return

    item_type = item.get("type")

    if item_type == "heading":
        level = item.get("level", 3)
        level = max(1, min(int(level), 6))

        text = item.get("text", "")

        if text:
            lines.append(f'{"#" * level} {text}')
            lines.append("")

    elif item_type == "paragraph":
        text = item.get("text", "")

        if text:
            lines.append(str(text).strip())
            lines.append("")

    elif item_type == "list":
        items = item.get("items", [])

        if isinstance(items, list):
            for value in items:
                lines.append(f"- {value}")

            lines.append("")

    elif item_type == "table":
        _render_table(item, lines)

    elif item_type == "image":
        _render_image(item, lines)

    elif item_type == "section":
        _render_section(item, lines)

    else:
        text = item.get("text")

        if text:
            lines.append(str(text).strip())
            lines.append("")


def _render_table(item: dict[str, Any], lines: list[str]) -> None:
    headers = item.get("headers", [])
    rows = item.get("rows", [])

    if not headers:
        return

    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines.append("| " + " | ".join(cell(h) for h in headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")

    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, list):
                values = row
            elif isinstance(row, dict):
                values = [row.get(header, "") for header in headers]
            else:
                continue

            values = list(values)

            if len(values) < len(headers):
                values.extend([""] * (len(headers) - len(values)))

            values = values[:len(headers)]

            lines.append(
                "| " + " | ".join(cell(value) for value in values) + " |"
            )

    lines.append("")


def _render_image(item: dict[str, Any], lines: list[str]) -> None:
    reference = (
        item.get("image_reference")
        or item.get("reference")
        or item.get("uri")
    )

    caption = item.get("caption") or item.get("alt") or "Image"

    if reference:
        lines.append(f"![{caption}]({reference})")
        lines.append("")