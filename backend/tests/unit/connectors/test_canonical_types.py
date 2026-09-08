#!/usr/bin/env python3
"""Unit tests for connectors/canonical_types.py -- pure functions, no I/O."""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from cce.connectors.base.canonical_types import (  # noqa: E402
    CANONICAL_TYPE_MAPPING, canonicalize_type, get_type_category,
)


class CanonicalizeTypeTests(unittest.TestCase):
    def test_snowflake_number_to_numeric(self):
        canonical, detail = canonicalize_type("NUMBER(18,2)", "snowflake")
        self.assertEqual(canonical, "NUMERIC")
        self.assertEqual(detail["precision"], 18)
        self.assertEqual(detail["scale"], 2)
        self.assertEqual(detail["source_type"], "NUMBER(18,2)")
        self.assertEqual(detail["source_database"], "snowflake")
        self.assertEqual(detail["category"], "decimal")

    def test_postgres_numeric_to_numeric(self):
        canonical, detail = canonicalize_type("numeric(18,2)", "postgres")
        self.assertEqual(canonical, "NUMERIC")
        self.assertEqual(detail["precision"], 18)
        self.assertEqual(detail["scale"], 2)

    def test_mysql_decimal_to_numeric(self):
        canonical, detail = canonicalize_type("DECIMAL(18,2)", "mysql")
        self.assertEqual(canonical, "NUMERIC")
        self.assertEqual(detail["precision"], 18)
        self.assertEqual(detail["scale"], 2)

    def test_text_types(self):
        for native in ["VARCHAR(255)", "TEXT", "CHARACTER VARYING", "text", "  varchar (10) "]:
            canonical, _ = canonicalize_type(native, "postgres")
            self.assertEqual(canonical, "TEXT", native)

    def test_varchar_length_is_recorded_not_precision(self):
        _, detail = canonicalize_type("VARCHAR(255)", "snowflake")
        self.assertEqual(detail["length"], 255)
        self.assertNotIn("precision", detail)

    def test_integer_types(self):
        for native in ["INT", "INTEGER", "BIGINT", "SMALLINT"]:
            canonical, _ = canonicalize_type(native, "snowflake")
            self.assertEqual(canonical, "INTEGER", native)

    def test_bare_type_has_no_precision_or_scale(self):
        canonical, detail = canonicalize_type("BIGINT", "mysql")
        self.assertEqual(canonical, "INTEGER")
        self.assertNotIn("precision", detail)
        self.assertNotIn("scale", detail)

    def test_unknown_type(self):
        canonical, detail = canonicalize_type("EXOTIC_TYPE", "snowflake")
        self.assertEqual(canonical, "UNKNOWN")
        self.assertIn("Type not recognized", detail["note"])
        self.assertEqual(detail["source_type"], "EXOTIC_TYPE")

    def test_snowflake_timestamp_ntz(self):
        canonical, detail = canonicalize_type("TIMESTAMP_NTZ(9)", "snowflake")
        self.assertEqual(canonical, "TIMESTAMP")
        self.assertEqual(detail["precision"], 9)

    def test_postgres_double_precision_multi_word_base(self):
        canonical, _ = canonicalize_type("double precision", "postgres")
        self.assertEqual(canonical, "FLOAT")

    def test_mysql_boolean_alias(self):
        canonical, _ = canonicalize_type("BOOL", "mysql")
        self.assertEqual(canonical, "BOOLEAN")

    def test_semi_structured_types(self):
        for native, db in [("VARIANT", "snowflake"), ("JSONB", "postgres"), ("JSON", "mysql")]:
            canonical, _ = canonicalize_type(native, db)
            self.assertEqual(canonical, "VARIANT", native)


class GetTypeCategoryTests(unittest.TestCase):
    def test_known_categories(self):
        self.assertEqual(get_type_category("NUMERIC"), "decimal")
        self.assertEqual(get_type_category("TEXT"), "string")
        self.assertEqual(get_type_category("TIMESTAMP"), "temporal")

    def test_unknown_canonical_type(self):
        self.assertEqual(get_type_category("NOT_A_REAL_TYPE"), "unknown")
        self.assertEqual(get_type_category("UNKNOWN"), "unknown")


class MappingCoverageTests(unittest.TestCase):
    def test_every_mapping_value_is_a_canonical_type(self):
        from cce.connectors.base.canonical_types import CANONICAL_TYPES
        for base, canonical in CANONICAL_TYPE_MAPPING.items():
            self.assertIn(canonical, CANONICAL_TYPES, "base type %r maps to non-canonical %r" % (base, canonical))


if __name__ == "__main__":
    unittest.main()
