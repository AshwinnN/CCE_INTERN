#!/usr/bin/env python3
"""Convert any fetch/parse output to the CanonicalDocument shape
(ingestion/models.py): {"metadata": {...}, "elements": [{"id", "type",
"text", ...}, ...]}.

Branches ONLY on kind ("structured" | "unstructured"), never on adapter --
the same discipline agents/connector_agent/router.py already documents for
routing ("branches ONLY on kind -- never on adapter/vendor name"), because
the shape difference here is structured-vs-unstructured, not vendor-specific.
`source_database` (structured only) is passed through to
connectors.canonical_types.canonicalize_type() as data, not branched on.
"""
from typing import Any, Dict, List, Optional


def normalize_to_canonical(payload: Optional[Dict[str, Any]], kind: str,
                            source_database: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
        Each element's metadata also carries a "columns" list with the
        canonicalized type (see connectors/canonical_types.py -- "Issue 5:
        Canonical Types") for every column, so a caller downstream of this
        normalizer (including CCE_SDK_ENDPOINT's payload) sees canonical
        types without depending on the metadata repository.
    source_database: required when kind == "structured" (ignored otherwise)
      -- the adapter name ("snowflake", "postgres", ...) canonicalize_type()
      needs to disambiguate a native type string; passed separately rather
      than read off the schema card because the schema card's own shape is
      deliberately adapter-agnostic (see StructuredConnector.get_schema_card()'s
      docstring).
    Returns None if payload is None (nothing to normalize -- an earlier
    node already recorded why).
    """
    if payload is None:
        return None

    if kind == "unstructured":
        return payload

    if kind == "structured":
        return _normalize_schema_card(payload, source_database)

    raise ValueError("normalize_to_canonical: unknown kind %r" % kind)


def _normalize_schema_card(schema_card: Dict[str, Any], source_database: Optional[str]) -> Dict[str, Any]:
    from connectors.canonical_types import canonicalize_type

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

        column_types = []
        for col in columns:
            native_type = col.get("type")
            data_type, type_detail = canonicalize_type(native_type, source_database or "")
            column_types.append({
                "name": col.get("name"),
                "native_type": native_type,
                "data_type": data_type,
                "type_detail": type_detail,
            })

        elements.append({
            "id": "schema_%s" % table.get("name"),
            "type": "table",
            "text": "%s (%d columns)" % (table.get("name"), len(columns)),
            "metadata": {"schema": schema, "table_name": table.get("name"),
                         "row_count": table.get("row_count"), "columns": column_types},
            "cells": cells,
        })

    return {"metadata": {"schema": schema}, "elements": elements}
