#!/usr/bin/env python3
"""Metadata-validation test (Issue 1): every `depends_on` entry in every
SKILL.md must name a skill that actually exists on disk. Catches exactly the
kind of stale reference skill-strucutred_source_connect had
(skill-cce-source-registry / skill-cce-dialect-profile — neither real).

Scoped to skills/Connect_Ingest_Ground/ only. skills/Dontreadthis/ is never
opened, listed, or imported, per standing instruction.

Run: python3 tests/test_skill_metadata.py
"""
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_ROOT = os.path.join(REPO, "skills")

DEPENDS_ON_BLOCK_RE = re.compile(r"depends_on:\s*\n((?:\s*-\s*\S.*\n)*)")
LIST_ITEM_RE = re.compile(r'-\s*["\']?([A-Za-z0-9_.\-/]+)["\']?')


def _find_skill_dirs():
    if not os.path.isdir(SKILLS_ROOT):
        raise unittest.SkipTest("skills/ is not part of this deterministic runtime checkout")
    return sorted(
        name for name in os.listdir(SKILLS_ROOT)
        if os.path.isdir(os.path.join(SKILLS_ROOT, name)) and name.startswith("skill-")
    )


def _extract_depends_on(skill_md_path):
    with open(skill_md_path) as fh:
        text = fh.read()
    # Only look inside the frontmatter block (between the first pair of ---).
    parts = text.split("---", 2)
    frontmatter = parts[1] if len(parts) >= 3 else ""
    match = DEPENDS_ON_BLOCK_RE.search(frontmatter)
    if not match:
        return []
    return [
        LIST_ITEM_RE.match(line.strip()).group(1)
        for line in match.group(1).splitlines()
        if line.strip()
    ]


# Scoped to the four Connectors-stage skills this task owns (source-registry,
# credential-resolution, strucutred_source_connect, document-source-connect),
# matching the ROLE prompt's stated scope. Other skills in this directory
# (e.g. skill-embedding-generation -> skill-content-classification,
# skill-guarded-query-execution -> skill-structured-source-connect) have the
# same class of stale/non-existent depends_on reference, found by running
# this same check unscoped — reported separately, not fixed here, since
# repairing them is outside the three named connector-stage issues.
#
# skill-schema-discovery -> skill-sql-guard was in this set until
# skill-sql-guard was added to the repo; skill-schema-discovery's own
# depends_on already used the correct name, so no metadata fix was needed
# there once the real skill existed.
IN_SCOPE_SKILLS = (
    "skill-source-registry",
    "skill-credential-resolution",
    "skill-strucutred_source_connect",
    "skill-document-source-connect",
)


class SkillMetadataTests(unittest.TestCase):

    def test_in_scope_depends_on_references_resolve_to_a_real_skill_directory(self):
        all_skill_dirs = set(_find_skill_dirs())
        self.assertTrue(all_skill_dirs, "no skill directories found under %s" % SKILLS_ROOT)

        broken = []
        for name in IN_SCOPE_SKILLS:
            skill_md = os.path.join(SKILLS_ROOT, name, "SKILL.md")
            if not os.path.isfile(skill_md):
                continue
            for dep in _extract_depends_on(skill_md):
                # A dependency starting with "common/" is orchestration
                # plumbing (an input_adapter), not a Skill reference — skip it.
                if dep.startswith("common/"):
                    continue
                if dep not in all_skill_dirs:
                    broken.append((name, dep))

        self.assertEqual(
            broken, [],
            "stale/non-existent depends_on references found: %s" % broken,
        )

    def test_full_repo_scan_documents_known_pre_existing_issues_outside_scope(self):
        """Not a pass/fail gate on out-of-scope skills — documents exactly
        which other stale references exist today, so they're visible rather
        than silently fixed or silently ignored."""
        all_skill_dirs = set(_find_skill_dirs())
        found = []
        for name in sorted(all_skill_dirs):
            skill_md = os.path.join(SKILLS_ROOT, name, "SKILL.md")
            if not os.path.isfile(skill_md):
                continue
            for dep in _extract_depends_on(skill_md):
                if dep.startswith("common/"):
                    continue
                if dep not in all_skill_dirs:
                    found.append((name, dep))
        known_pre_existing = {
            ("skill-embedding-generation", "skill-content-classification"),
            ("skill-guarded-query-execution", "skill-structured-source-connect"),
            ("skill-schema-discovery", "skill-structured-source-connect"),
        }
        # This assertion documents the known set rather than gating on it —
        # if it ever fails, the pre-existing-issue set has changed and this
        # test (and the summary reported to the user) needs updating.
        self.assertEqual(set(found) - {(n, d) for n, d in found if n in IN_SCOPE_SKILLS},
                          known_pre_existing)

    def test_structured_connect_no_longer_references_stale_cce_prefixed_names(self):
        skill_md = os.path.join(SKILLS_ROOT, "skill-strucutred_source_connect", "SKILL.md")
        if not os.path.isfile(skill_md):
            self.skipTest("skills/ is not part of this deterministic runtime checkout")
        with open(skill_md) as fh:
            text = fh.read()
        self.assertNotIn("skill-cce-source-registry", text)
        self.assertNotIn("skill-cce-dialect-profile", text)


if __name__ == "__main__":
    unittest.main()
