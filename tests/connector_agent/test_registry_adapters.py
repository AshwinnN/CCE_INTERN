#!/usr/bin/env python3
"""Tests for common/known_adapters.py and the registry_to_*_connect
transforms, exercised together with the real skill-source-registry
validator (not a mock of it)."""
import copy
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from common.known_adapters import StubAdapterRegistryProvider  # noqa: E402
from common.registry_to_structured_connect import to_structured_connect_registry  # noqa: E402
from common.registry_to_document_connect import validate_document_connect_registry  # noqa: E402
from common.skill_loader import load_skill_function  # noqa: E402


class KnownAdaptersTests(unittest.TestCase):

    def setUp(self):
        self.provider = StubAdapterRegistryProvider()
        self.registry_validate = load_skill_function(
            "skill-source-registry", "validate_registry_entry.py", "validate"
        )

    def test_unknown_adapter_returns_none(self):
        self.assertIsNone(self.provider.get("does-not-exist"))

    def test_returned_record_is_a_copy_not_shared_state(self):
        a = self.provider.get("snowflake")
        a["capabilities"]["write_probe"] = False
        b = self.provider.get("snowflake")
        self.assertTrue(b["capabilities"]["write_probe"])

    def test_every_seeded_structured_adapter_passes_real_registry_validation(self):
        for adapter in ("snowflake", "postgres", "databricks", "bigquery"):
            entry = self.provider.get(adapter)
            descriptor = self.registry_validate(entry)
            self.assertEqual(descriptor["status"], "READY", "%s: %s" % (adapter, descriptor))
            self.assertEqual(descriptor["kind"], "structured")

    def test_every_seeded_unstructured_adapter_passes_real_registry_validation(self):
        for adapter in ("google-drive", "gmail", "sharepoint", "slack", "confluence", "local-fs"):
            entry = self.provider.get(adapter)
            descriptor = self.registry_validate(entry)
            self.assertEqual(descriptor["status"], "READY", "%s: %s" % (adapter, descriptor))
            self.assertEqual(descriptor["kind"], "unstructured")

    def test_structured_descriptor_reshapes_into_exact_connect_shape(self):
        entry = self.provider.get("snowflake")
        descriptor = self.registry_validate(entry)
        reshaped = to_structured_connect_registry(descriptor)
        self.assertEqual(reshaped["status"], "OK")
        self.assertEqual(set(reshaped["registry"].keys()), {"snowflake"})
        self.assertEqual(reshaped["registry"]["snowflake"]["dialect"], "snowflake")

    def test_unstructured_descriptor_validates_without_reshape(self):
        entry = self.provider.get("google-drive")
        descriptor = self.registry_validate(entry)
        result = validate_document_connect_registry(descriptor)
        self.assertEqual(result["status"], "OK")
        self.assertIn("write_probe", result["capabilities"])

    def test_structured_transform_rejects_an_unstructured_descriptor(self):
        entry = self.provider.get("google-drive")
        descriptor = self.registry_validate(entry)
        reshaped = to_structured_connect_registry(descriptor)
        self.assertEqual(reshaped["status"], "ERROR")
        self.assertEqual(reshaped["error_code"], "REGISTRY_KIND_MISMATCH")

    def test_document_transform_rejects_a_structured_descriptor(self):
        entry = self.provider.get("snowflake")
        descriptor = self.registry_validate(entry)
        result = validate_document_connect_registry(descriptor)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error_code"], "REGISTRY_KIND_MISMATCH")


if __name__ == "__main__":
    unittest.main()
