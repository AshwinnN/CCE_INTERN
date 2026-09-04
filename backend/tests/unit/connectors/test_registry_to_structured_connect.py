#!/usr/bin/env python3
"""Contract tests for common/registry_to_structured_connect.py (Issue 2).

Run: python3 tests/test_registry_to_structured_connect.py
"""
import copy
import inspect
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "common"))

from registry_to_structured_connect import to_structured_connect_registry  # noqa: E402
import registry_to_structured_connect as transform_module  # noqa: E402

VALID_DESCRIPTOR = {
    "adapter": "snowflake",
    "kind": "structured",
    "dialect": "snowflake",
    "capabilities": {
        "write_probe": True,
        "statement_timeout": True,
        "row_cap": True,
        "schema_scope": True,
    },
    "schema_version": "1.0",
    "deprecated": False,
    "status": "READY",
    "violated_rule": None,
}


class RegistryToStructuredConnectTests(unittest.TestCase):

    def test_valid_descriptor_transforms_to_exact_expected_shape(self):
        result = to_structured_connect_registry(VALID_DESCRIPTOR)
        self.assertEqual(result["status"], "OK")
        self.assertIsNone(result["error_code"])
        self.assertEqual(result["registry"], {
            "snowflake": {
                "dialect": "snowflake",
                "supports": {
                    "write_probe": True,
                    "statement_timeout": True,
                    "row_cap": True,
                    "schema_scope": True,
                },
            }
        })

    def test_kind_not_structured_fails(self):
        d = copy.deepcopy(VALID_DESCRIPTOR)
        d["kind"] = "unstructured"
        result = to_structured_connect_registry(d)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error_code"], "REGISTRY_KIND_MISMATCH")
        self.assertIsNone(result["registry"])

    def test_status_not_active_fails(self):
        d = copy.deepcopy(VALID_DESCRIPTOR)
        d["status"] = "REJECTED"
        result = to_structured_connect_registry(d)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error_code"], "REGISTRY_INACTIVE")
        self.assertIsNone(result["registry"])

    def test_deprecated_true_fails(self):
        d = copy.deepcopy(VALID_DESCRIPTOR)
        d["deprecated"] = True
        result = to_structured_connect_registry(d)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error_code"], "REGISTRY_DEPRECATED")
        self.assertIsNone(result["registry"])

    def test_nonnull_violated_rule_fails(self):
        d = copy.deepcopy(VALID_DESCRIPTOR)
        d["violated_rule"] = "REG05"
        result = to_structured_connect_registry(d)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error_code"], "REGISTRY_RULE_VIOLATION")
        self.assertIsNone(result["registry"])

    def test_missing_dialect_fails(self):
        d = copy.deepcopy(VALID_DESCRIPTOR)
        d["dialect"] = None
        result = to_structured_connect_registry(d)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error_code"], "REGISTRY_DIALECT_MISSING")
        self.assertIsNone(result["registry"])

    def test_unsupported_schema_version_fails(self):
        d = copy.deepcopy(VALID_DESCRIPTOR)
        d["schema_version"] = "2.0"
        result = to_structured_connect_registry(d)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error_code"], "REGISTRY_SCHEMA_UNSUPPORTED")
        self.assertIsNone(result["registry"])

    def test_missing_adapter_fails(self):
        d = copy.deepcopy(VALID_DESCRIPTOR)
        d["adapter"] = None
        result = to_structured_connect_registry(d)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error_code"], "REGISTRY_ADAPTER_MISSING")
        self.assertIsNone(result["registry"])

    def test_invalid_capabilities_fails(self):
        d = copy.deepcopy(VALID_DESCRIPTOR)
        d["capabilities"] = {"write_probe": True}  # missing required keys
        result = to_structured_connect_registry(d)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error_code"], "REGISTRY_CAPABILITIES_INVALID")
        self.assertIsNone(result["registry"])

    def test_every_error_path_returns_null_registry_never_a_fallback_shape(self):
        """An invalid explicitly-supplied registry must never resolve to
        something a caller could mistake for a usable registry payload."""
        bad_variants = [
            {**VALID_DESCRIPTOR, "kind": "unstructured"},
            {**VALID_DESCRIPTOR, "status": "REJECTED"},
            {**VALID_DESCRIPTOR, "deprecated": True},
            {**VALID_DESCRIPTOR, "violated_rule": "REG01"},
            {**VALID_DESCRIPTOR, "dialect": None},
            {**VALID_DESCRIPTOR, "schema_version": "9.9"},
        ]
        for variant in bad_variants:
            result = to_structured_connect_registry(variant)
            self.assertEqual(result["status"], "ERROR")
            self.assertIsNone(result["registry"])

    def test_module_has_no_default_registry_fallback_path(self):
        """Structural guarantee: this transform has no code path that could
        return DEFAULT_REGISTRY-shaped data on failure, because it contains
        no reference to a default registry at all."""
        source = inspect.getsource(transform_module)
        self.assertNotIn("DEFAULT_REGISTRY", source)

    def test_output_shape_is_stable_regardless_of_outcome(self):
        ok = to_structured_connect_registry(VALID_DESCRIPTOR)
        err = to_structured_connect_registry({**VALID_DESCRIPTOR, "kind": "bogus"})
        self.assertEqual(set(ok.keys()), {"status", "error_code", "registry"})
        self.assertEqual(set(err.keys()), {"status", "error_code", "registry"})


if __name__ == "__main__":
    unittest.main()
