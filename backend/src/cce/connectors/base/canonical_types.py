#!/usr/bin/env python3
"""Vendor type name -> CCE canonical type. See
canonical_types_implementation_diagram.md ("Issue 5: Canonical Types") for
the motivating problem: the same logical type is spelled differently by
every vendor (Snowflake NUMBER(18,2), Postgres numeric(18,2), MySQL
DECIMAL(18,2)) and CCE needs one vocabulary to query/reason across them.

Deliberately NOT called from connectors/snowflake/connector.py (or any
future connectors/<adapter>/connector.py): StructuredConnector.get_schema_card()
stays vendor-neutral (raw native types only, see connectors/base/connector.py's
module docstring), and canonicalization is applied once, downstream, by
common/tools/document_normalizer.py and repository/postgresql_metadata_repository.py.
That keeps this the single call site instead of one per adapter -- a future
Postgres/MySQL adapter needs zero canonicalization code of its own.

9 canonical types (+ UNKNOWN as the explicit, never-raise fallback for a
base type this module doesn't recognize):
    TEXT, INTEGER, NUMERIC, FLOAT, BOOLEAN, DATE, TIMESTAMP, BINARY, VARIANT
"""
import re
from typing import Any, Dict, Optional, Tuple

CANONICAL_TYPES = (
    "TEXT", "INTEGER", "NUMERIC", "FLOAT", "BOOLEAN",
    "DATE", "TIMESTAMP", "BINARY", "VARIANT",
)

_TYPE_CATEGORY = {
    "TEXT": "string",
    "INTEGER": "integer",
    "NUMERIC": "decimal",
    "FLOAT": "floating",
    "BOOLEAN": "boolean",
    "DATE": "temporal",
    "TIMESTAMP": "temporal",
    "BINARY": "binary",
    "VARIANT": "semi-structured",
    "UNKNOWN": "unknown",
}

# Keyed by normalized base type name (upper-cased, single-spaced, parameters
# stripped -- see _split_native_type()). Shared across vendors: base names
# rarely collide in meaning, so one flat dict covers Snowflake/Postgres/MySQL
# rather than three parallel ones the lookup would have to pick between.
CANONICAL_TYPE_MAPPING: Dict[str, str] = {
    # --- integer ---
    "TINYINT": "INTEGER", "BYTEINT": "INTEGER", "SMALLINT": "INTEGER",
    "MEDIUMINT": "INTEGER", "INT": "INTEGER", "INT2": "INTEGER",
    "INT4": "INTEGER", "INTEGER": "INTEGER", "BIGINT": "INTEGER",
    "INT8": "INTEGER", "SERIAL": "INTEGER", "SMALLSERIAL": "INTEGER",
    "BIGSERIAL": "INTEGER", "YEAR": "INTEGER",

    # --- numeric / decimal (fixed precision) ---
    "NUMBER": "NUMERIC", "DECIMAL": "NUMERIC", "NUMERIC": "NUMERIC",
    "DEC": "NUMERIC", "MONEY": "NUMERIC",

    # --- floating point ---
    "FLOAT": "FLOAT", "FLOAT4": "FLOAT", "FLOAT8": "FLOAT",
    "DOUBLE": "FLOAT", "DOUBLE PRECISION": "FLOAT", "REAL": "FLOAT",

    # --- text ---
    "VARCHAR": "TEXT", "CHAR": "TEXT", "CHARACTER": "TEXT",
    "CHARACTER VARYING": "TEXT", "NVARCHAR": "TEXT", "NCHAR": "TEXT",
    "STRING": "TEXT", "TEXT": "TEXT", "TINYTEXT": "TEXT",
    "MEDIUMTEXT": "TEXT", "LONGTEXT": "TEXT", "UUID": "TEXT",
    "ENUM": "TEXT", "SET": "TEXT",

    # --- boolean ---
    "BOOLEAN": "BOOLEAN", "BOOL": "BOOLEAN",

    # --- date (no time component) ---
    "DATE": "DATE",

    # --- timestamp (date+time; TIME alone has no dedicated canonical type
    # among the 9, so it maps here too -- see module docstring) ---
    "DATETIME": "TIMESTAMP", "TIMESTAMP": "TIMESTAMP", "TIME": "TIMESTAMP",
    "TIMESTAMP_LTZ": "TIMESTAMP", "TIMESTAMP_NTZ": "TIMESTAMP",
    "TIMESTAMP_TZ": "TIMESTAMP", "TIMESTAMPTZ": "TIMESTAMP",
    "TIMESTAMP WITHOUT TIME ZONE": "TIMESTAMP",
    "TIMESTAMP WITH TIME ZONE": "TIMESTAMP",

    # --- binary ---
    "BINARY": "BINARY", "VARBINARY": "BINARY", "BYTEA": "BINARY",
    "BLOB": "BINARY", "TINYBLOB": "BINARY", "MEDIUMBLOB": "BINARY",
    "LONGBLOB": "BINARY", "BIT": "BINARY", "BIT VARYING": "BINARY",

    # --- semi-structured ---
    "VARIANT": "VARIANT", "OBJECT": "VARIANT", "ARRAY": "VARIANT",
    "JSON": "VARIANT", "JSONB": "VARIANT",
}

# Canonical types whose numeric parameter is a length (characters/bytes),
# not a (precision, scale) pair -- everything else with a single parameter
# is treated as precision.
_LENGTH_TYPED_CANONICALS = frozenset({"TEXT", "BINARY"})

_PARAM_PATTERN = re.compile(r"^(.*?)\s*\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\)\s*$")


def _split_native_type(native_type: str) -> Tuple[str, Optional[int], Optional[int]]:
    """"NUMBER(18,2)" -> ("NUMBER", 18, 2). "VARCHAR(255)" -> ("VARCHAR", 255,
    None). "TEXT" -> ("TEXT", None, None). Base name is normalized
    (upper-cased, internal whitespace collapsed to single spaces) so
    "character varying" and "CHARACTER  VARYING" both match."""
    normalized = re.sub(r"\s+", " ", native_type.strip()).upper()
    match = _PARAM_PATTERN.match(normalized)
    if match:
        base, p1, p2 = match.group(1).strip(), match.group(2), match.group(3)
        return base, int(p1), (int(p2) if p2 is not None else None)
    return normalized, None, None


def canonicalize_type(native_type: str, source_database: str) -> Tuple[str, Dict[str, Any]]:
    """Map one vendor type string to (canonical_type, type_detail).

    type_detail always carries "source_type" (the original, unmodified
    native_type string), "source_database", and "category". "precision"/
    "scale" (NUMERIC-style) or "length" (TEXT/BINARY-style) are included
    only when the native type actually specified a parameter.

    Never raises for an unrecognized type -- returns ("UNKNOWN", {...,
    "note": "..."}) instead, matching this repo's convention of recording
    an unmapped input rather than failing the caller
    (common/tools/dlp_classifier.py's classify_text() does the same for an
    unrecognized pattern).
    """
    base, p1, p2 = _split_native_type(native_type)
    canonical = CANONICAL_TYPE_MAPPING.get(base)

    if canonical is None:
        return "UNKNOWN", {
            "note": "Type not recognized: base type %r is not in CANONICAL_TYPE_MAPPING "
                    "for source_database=%r" % (base, source_database),
            "source_type": native_type,
            "source_database": source_database,
            "category": _TYPE_CATEGORY["UNKNOWN"],
        }

    detail: Dict[str, Any] = {
        "source_type": native_type,
        "source_database": source_database,
        "category": _TYPE_CATEGORY[canonical],
    }
    if p1 is not None:
        if canonical in _LENGTH_TYPED_CANONICALS:
            detail["length"] = p1
        else:
            detail["precision"] = p1
            if p2 is not None:
                detail["scale"] = p2

    return canonical, detail


def get_type_category(canonical_type: str) -> str:
    """"NUMERIC" -> "decimal", "TEXT" -> "string", etc. Returns "unknown"
    for any input that isn't one of CANONICAL_TYPES (including the literal
    string "UNKNOWN")."""
    return _TYPE_CATEGORY.get(canonical_type, _TYPE_CATEGORY["UNKNOWN"])
