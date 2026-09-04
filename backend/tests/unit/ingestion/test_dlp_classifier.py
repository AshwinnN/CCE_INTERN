#!/usr/bin/env python3
"""dlp_classifier.py is a deliberate stub (see its module docstring) --
these tests pin down the stub's contract (shape + always-PUBLIC/no-op
behavior) so a future real implementation is a visible, intentional change
to this test file, not a silent behavior drift."""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from cce.security.dlp import (  # noqa: E402
    classify_text, redact_text, get_dlp_confidence_threshold, DEFAULT_DLP_CONFIDENCE_THRESHOLD,
)


class DlpClassifierStubTests(unittest.TestCase):

    def test_classify_text_always_reports_public(self):
        result = classify_text("My SSN is 123-45-6789")
        self.assertEqual(result, {"sensitivity": "PUBLIC", "patterns_found": [], "confidence": 1.0})

    def test_classify_text_ignores_column_name_hint(self):
        result = classify_text("normal text", column_name="customer_pii_id")
        self.assertEqual(result["sensitivity"], "PUBLIC")

    def test_redact_text_is_a_no_op(self):
        text = "SSN: 123-45-6789, CC: 4532-1111-2222-3333"
        self.assertEqual(redact_text(text), text)

    def test_confidence_threshold_defaults_when_env_unset(self):
        os.environ.pop("CCE_DLP_CONFIDENCE_THRESHOLD", None)
        self.assertEqual(get_dlp_confidence_threshold(), DEFAULT_DLP_CONFIDENCE_THRESHOLD)

    def test_confidence_threshold_reads_env_override(self):
        os.environ["CCE_DLP_CONFIDENCE_THRESHOLD"] = "0.42"
        try:
            self.assertEqual(get_dlp_confidence_threshold(), 0.42)
        finally:
            del os.environ["CCE_DLP_CONFIDENCE_THRESHOLD"]

    def test_confidence_threshold_falls_back_on_unparseable_value(self):
        os.environ["CCE_DLP_CONFIDENCE_THRESHOLD"] = "not-a-number"
        try:
            self.assertEqual(get_dlp_confidence_threshold(), DEFAULT_DLP_CONFIDENCE_THRESHOLD)
        finally:
            del os.environ["CCE_DLP_CONFIDENCE_THRESHOLD"]


if __name__ == "__main__":
    unittest.main()
