"""Readable evidence envelope; metadata also travels as structured fields."""
import json


def render_markdown(content: str, metadata: dict) -> str:
    lines = ["# Evidence", "", "## Metadata"]
    for key, value in sorted(metadata.items()):
        if value is not None and value != "":
            rendered = json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (list, dict)) else str(value)
            lines.append(f"- {key}: {rendered.replace(chr(10), ' ')}")
    return "\n".join([*lines, "", "## Content", content])
