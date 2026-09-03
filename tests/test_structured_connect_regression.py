#!/usr/bin/env python3
"""Regression test: skill-strucutred_source_connect's own test-suite.json
must still pass exactly, after removing the dead `role` field from its
fixtures (Issue 3) and after the frontmatter change (Issue 1). Proves the
role removal was behavior-neutral, per the script never reading it.

Run: python3 tests/test_structured_connect_regression.py
"""
import importlib.util
import json
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_DIR = os.path.join(REPO, "skills", "skill-strucutred_source_connect")


def _load_validate():
    path = os.path.join(SKILL_DIR, "scripts", "validate_source_profile.py")
    spec = importlib.util.spec_from_file_location("validate_source_profile", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.validate, mod.DEFAULT_REGISTRY


class StructuredConnectRegressionTests(unittest.TestCase):

    def test_every_test_suite_case_matches_expected_output(self):
        if not os.path.isfile(os.path.join(SKILL_DIR, "scripts", "validate_source_profile.py")):
            self.skipTest("skill-strucutred_source_connect scripts are not part of deterministic runtime")
        validate, default_registry = _load_validate()
        with open(os.path.join(SKILL_DIR, "validation", "test-suite.json")) as fh:
            suite = json.load(fh)

        failures = []
        for case in suite["test_cases"]:
            input_path = os.path.join(SKILL_DIR, "validation", case["input_file"])
            with open(input_path) as fh:
                profile = json.load(fh)
            self.assertNotIn("role", profile,
                              "%s still carries the removed `role` field" % case["id"])
            actual = validate(profile, default_registry)
            if actual != case["expected"]:
                failures.append((case["id"], case["expected"], actual))

        self.assertEqual(failures, [], "mismatches: %s" % failures)


if __name__ == "__main__":
    unittest.main()
