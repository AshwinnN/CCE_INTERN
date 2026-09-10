"""Citation labels from supplied coordinates, never inferred physical pages."""
from pathlib import PurePosixPath


def citation_coordinates(metadata):
    keys = ("document_id", "document_version", "page_number", "section_path", "element_id", "chunk_id", "char_start", "char_end", "bbox", "confidence", "mime_type", "paragraph_index", "bbox_coordinate_system", "render_scale")
    return {key: metadata[key] for key in keys if metadata.get(key) is not None}


def citation_label(metadata):
    name = metadata.get("original_filename") or metadata.get("source_uri") or metadata.get("source_ref") or metadata.get("document_id") or "Evidence"
    name = PurePosixPath(str(name).replace("\\", "/")).name
    parts = []
    if metadata.get("page_number") is not None:
        parts.append(f"p. {metadata['page_number']}")
    section = metadata.get("section_path")
    if section:
        parts.append(" > ".join(section) if isinstance(section, list) else str(section))
    if metadata.get("paragraph_index") is not None:
        parts.append(f"paragraph {metadata['paragraph_index'] + 1}")
    elif metadata.get("element_id"):
        parts.append(f"element {metadata['element_id']}")
    return name + (" — " + ", ".join(parts) if parts else "")
