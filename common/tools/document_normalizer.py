#!/usr/bin/env python3
"""Convert any fetch/parse output to the CanonicalDocument shape
(ingestion/models.py): {"metadata": {...}, "elements": [{"id", "type",
"text", ...}, ...]}.

Branches ONLY on kind ("structured" | "unstructured"), never on adapter --
the same discipline agents/connector_agent/router.py already documents for
routing ("branches ONLY on kind -- never on adapter/vendor name"), because
the shape difference here is structured-vs-unstructured, not vendor-specific.
"""
from typing import Any, Dict, List, Optional


def normalize_to_canonical(payload: Optional[Dict[str, Any]], kind: str) -> Optional[Dict[str, Any]]:
    """
    payload:
      - unstructured: the parsed_doc dict from ingestion.parsers (already a
        CanonicalDocument.model_dump() -- ingestion/parsers/* build this
        shape directly). Passed through unchanged.
      - structured: the schema-card dict returned by
        connectors.base.connector.StructuredConnector.get_schema_card()
        (via common.tools.source_connector.fetch_structured()), shaped
        {"schema": str, "tables": [{"name", "columns": [{"name", "type",
        "nullable"}, ...], "row_count", "sample_row"}, ...]} -- identical
        for every connectors/ adapter. Converted into one "table"-type
        element per table, one cell per column (col 0) plus, where a
        sample row exists, its per-column value (col 1) -- the only place
        real source data appears in a schema card, so it's the one place
        classify_for_dlp_node's cell-level scan actually has PII to find.
    Returns None if payload is None (nothing to normalize -- an earlier
    node already recorded why).
    """
    if payload is None:
        return None

    if kind == "unstructured":
        return payload

    if kind == "structured":
        return _normalize_schema_card(payload)

    raise ValueError("normalize_to_canonical: unknown kind %r" % kind)


def _normalize_schema_card(schema_card: Dict[str, Any]) -> Dict[str, Any]:
    schema = schema_card.get("schema")
    elements: List[Dict[str, Any]] = []

    for table in schema_card.get("tables", []):
        columns = table.get("columns", [])
        sample_row = table.get("sample_row") or {}

        cells = [
            {"row": i, "col": 0, "text": "%s (%s)" % (col.get("name"), col.get("type"))}
            for i, col in enumerate(columns)
        ]
        cells += [
            {"row": i, "col": 1, "text": str(sample_row[col["name"]])}
            for i, col in enumerate(columns)
            if col.get("name") in sample_row and sample_row[col["name"]] is not None
        ]

        elements.append({
            "id": "schema_%s" % table.get("name"),
            "type": "table",
            "text": "%s (%d columns)" % (table.get("name"), len(columns)),
            "metadata": {"schema": schema, "table_name": table.get("name"),
                         "row_count": table.get("row_count")},
            "cells": cells,
        })

    return {"metadata": {"schema": schema}, "elements": elements}
