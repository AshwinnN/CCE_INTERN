from copy import deepcopy

import pytest
import tiktoken

from cce.integrations.agentic_plane.chunking import payload_chunks
from cce.integrations.agentic_plane.rendering import render_markdown
from cce.runtime.citations import citation_coordinates, citation_label


def test_recursive_chunks_preserve_text_offsets_overlap_and_identity():
    text = "First paragraph with enough detail. " * 100
    payload = dict(workspace_id="w", source_id="s", document_id="d", revision="v1", blocks=[
        dict(id="h", type="heading", text="Returns", metadata={"level": 1}, children=[
            dict(id="p", type="paragraph", text=text, page_number=7, bbox={"x0": 1}, confidence=.9)])])
    original = deepcopy(payload)
    chunks = list(payload_chunks(payload, target_tokens=60, overlap_tokens=10))
    assert payload == original
    assert chunks == list(payload_chunks(payload, target_tokens=60, overlap_tokens=10))
    paragraphs = [c for c in chunks if c["metadata"]["element_id"] == "p"]
    encoding = tiktoken.get_encoding("cl100k_base")
    covered = 0
    for chunk in paragraphs:
        m = chunk["metadata"]
        assert m["char_start"] <= covered
        covered = m["char_end"]
        assert text[m["char_start"]:m["char_end"]] == chunk["chunk_text"]
        assert len(encoding.encode(chunk["chunk_text"])) <= 60
        assert m["section_path"] == ["Returns"] and m["page_number"] == 7
        assert m["bbox"] == {"x0": 1} and m["confidence"] == .9
    assert covered == len(text)
    assert paragraphs[1]["metadata"]["char_start"] < paragraphs[0]["metadata"]["char_end"]
    payload["revision"] = "v2"
    assert {c["metadata"]["chunk_id"] for c in chunks}.isdisjoint(
        c["metadata"]["chunk_id"] for c in payload_chunks(payload, target_tokens=60, overlap_tokens=10))


def test_atomic_table_and_section_boundaries():
    payload = {"blocks": [
        {"id": "a", "type": "heading", "text": "A"},
        {"id": "t", "type": "table", "cells": [{"row": 0, "col": 0, "text": "Name"}, {"row": 1, "col": 0, "text": "Value"}]},
        {"id": "b", "type": "heading", "text": "B"},
        {"id": "p", "text": "Unrelated paragraph"}]}
    chunks = list(payload_chunks(payload))
    table = [c for c in chunks if c["metadata"]["element_id"] == "t"]
    assert len(table) == 1
    assert "| Name |\n| --- |\n| Value |" == table[0]["chunk_text"]
    assert table[0]["metadata"]["section_path"] == ["A"]
    assert chunks[-1]["metadata"]["section_path"] == ["B"]
    assert chunks[-1]["chunk_text"] == "Unrelated paragraph"


def test_oversized_tables_have_no_overlap():
    chunks = list(payload_chunks({"blocks": [{"id": "t", "type": "table", "text": "cell " * 100}]}, target_tokens=20, overlap_tokens=5))
    assert len(chunks) > 1
    for previous, current in zip(chunks, chunks[1:]):
        assert previous["metadata"]["char_end"] == current["metadata"]["char_start"]


def test_markdown_and_semantic_citations_do_not_invent_pages():
    metadata = {"document_id": "Document.docx", "element_id": "4", "section_path": ["Returns", "Eligibility"]}
    assert citation_label(metadata) == "Document.docx — Returns > Eligibility, element 4"
    assert "page_number" not in citation_coordinates(metadata)
    markdown = render_markdown("Body", metadata)
    assert "# Evidence" in markdown and "## Content\nBody" in markdown
    assert "document_id: Document.docx" in markdown
    metadata.update(document_id="Policy.pdf", page_number=7)
    assert "p. 7" in citation_label(metadata)


@pytest.mark.parametrize("target,overlap", [(0, 0), (10, 10), (10, -1)])
def test_invalid_chunk_configuration(target, overlap):
    with pytest.raises(ValueError):
        list(payload_chunks({}, target_tokens=target, overlap_tokens=overlap))
