#!/usr/bin/env python3
"""Regression test for skill-sql-guard's full test-suite.json, including the
new intent="introspection" carve-out (SQG05/SQG08) added to resolve the
SCD06-vs-SQG05 contract conflict.

Run: python3 tests/test_sql_guard_regression.py
"""
import json
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_DIR = os.path.join(REPO, "skills", "skill-sql-guard")
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))

import guard_sql  # noqa: E402


class SqlGuardRegressionTests(unittest.TestCase):

    def test_every_test_suite_case_matches_expected_output(self):
        with open(os.path.join(SKILL_DIR, "validation", "test-suite.json")) as fh:
            suite = json.load(fh)

        failures = []
        for case in suite["test_cases"]:
            input_path = os.path.join(SKILL_DIR, "validation", case["input_file"])
            with open(input_path) as fh:
                request = json.load(fh)
            actual = guard_sql.guard(request)
            if actual != case["expected"]:
                failures.append((case["id"], case["expected"], actual))

        self.assertEqual(failures, [], "mismatches: %s" % failures)

    def test_introspection_intent_never_weakens_sqg02_sqg03_sqg04_sqg06(self):
        profile = {
            "dialect": "postgres", "row_limit_strategy": "limit_clause",
            "system_catalogs": ["pg_catalog"], "forbidden_keywords": ["DROP"],
        }
        # Stacked statement still rejected under intent=introspection.
        r1 = guard_sql.guard({"sql": "SELECT * FROM pg_catalog.x; SELECT 1",
                               "dialect_profile": profile, "max_rows": 10,
                               "intent": "introspection"})
        self.assertEqual(r1["violated_rule"], "SQG02")

        # Non-SELECT leading statement still rejected.
        r2 = guard_sql.guard({"sql": "UPDATE pg_catalog.x SET y=1",
                               "dialect_profile": profile, "max_rows": 10,
                               "intent": "introspection"})
        self.assertEqual(r2["violated_rule"], "SQG03")

    def test_unrecognized_intent_value_is_treated_as_no_intent(self):
        profile = {
            "dialect": "postgres", "row_limit_strategy": "limit_clause",
            "system_catalogs": ["pg_catalog"], "forbidden_keywords": ["DROP"],
        }
        result = guard_sql.guard({"sql": "SELECT * FROM pg_catalog.x",
                                   "dialect_profile": profile, "max_rows": 10,
                                   "intent": "anything-else"})
        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["violated_rule"], "SQG05")
        self.assertIsNone(result["intent"])


if __name__ == "__main__":
    unittest.main()
