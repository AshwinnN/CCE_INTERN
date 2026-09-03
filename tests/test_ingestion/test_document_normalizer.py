#!/usr/bin/env python3
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from common.tools.document_normalizer import normalize_to_canonical  # noqa: E402


class DocumentNormalizerTests(unittest.TestCase):

    def test_none_payload_passes_through_as_none(self):
        self.assertIsNone(normalize_to_canonical(None, "unstructured"))

    def test_unstructured_payload_passes_through_unchanged(self):
        payload = {"metadata": {"document_id": "d1"}, "elements": [{"id": "e1", "text": "hi"}]}
        self.assertIs(normalize_to_canonical(payload, "unstructured"), payload)

    def test_structured_schema_card_produces_one_element_per_table(self):
        schema_card = {
            "schema": "PUBLIC",
            "tables": [
                {"name": "CUSTOMERS",
                 "columns": [{"name": "EMAIL", "type": "VARCHAR", "nullable": True},
                             {"name": "SSN", "type": "VARCHAR", "nullable": True}],
                 "row_count": 1000, "sample_row": None},
            ],
        }
        result = normalize_to_canonical(schema_card, "structured")
        self.assertEqual(result["metadata"], {"schema": "PUBLIC"})
        self.assertEqual(len(result["elements"]), 1)
        el = result["elements"][0]
        self.assertEqual(el["id"], "schema_CUSTOMERS")
        self.assertEqual(el["type"], "table")
        self.assertEqual(el["text"], "CUSTOMERS (2 columns)")
        self.assertEqual(el["metadata"]["row_count"], 1000)

    def test_columns_become_col_0_cells(self):
        schema_card = {
            "schema": "PUBLIC",
            "tables": [{"name": "T1",
                        "columns": [{"name": "A", "type": "INT", "nullable": False}],
                        "row_count": None, "sample_row": None}],
        }
        result = normalize_to_canonical(schema_card, "structured")
        cells = result["elements"][0]["cells"]
        self.assertEqual(cells, [{"row": 0, "col": 0, "text": "A (INT)"}])

    def test_sample_row_values_become_col_1_cells(self):
        schema_card = {
            "schema": "PUBLIC",
            "tables": [{"name": "T1",
                        "columns": [{"name": "SSN", "type": "VARCHAR", "nullable": True}],
                        "row_count": 1, "sample_row": {"SSN": "123-45-6789"}}],
        }
        result = normalize_to_canonical(schema_card, "structured")
        cells = result["elements"][0]["cells"]
        self.assertIn({"row": 0, "col": 1, "text": "123-45-6789"}, cells)

    def test_sample_row_missing_a_column_value_produces_no_col_1_cell_for_it(self):
        schema_card = {
            "schema": "PUBLIC",
            "tables": [{"name": "T1",
                        "columns": [{"name": "A", "type": "INT", "nullable": True},
                                    {"name": "B", "type": "INT", "nullable": True}],
                        "row_count": 1, "sample_row": {"A": 1}}],
        }
        result = normalize_to_canonical(schema_card, "structured")
        col1_cells = [c for c in result["elements"][0]["cells"] if c["col"] == 1]
        self.assertEqual(col1_cells, [{"row": 0, "col": 1, "text": "1"}])

    def test_no_tables_produces_no_elements(self):
        schema_card = {"schema": "EMPTY", "tables": []}
        result = normalize_to_canonical(schema_card, "structured")
        self.assertEqual(result["elements"], [])

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            normalize_to_canonical({"schema": "S", "tables": []}, "bogus")


if __name__ == "__main__":
    unittest.main()
