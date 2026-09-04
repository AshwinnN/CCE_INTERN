#!/usr/bin/env python3
"""Validate the target CCE skill architecture."""

from pathlib import Path
import re
import unittest


BACKEND = Path(__file__).resolve().parents[3]
SKILLS_ROOT = BACKEND / "skills"
EXPECTED_SKILLS = {
    "context_resolution",
    "entity_resolution",
    "semantic_mapping",
    "policy_interpretation",
    "sql_generation",
}

DEPENDS_ON_BLOCK_RE = re.compile(r"depends_on:\s*\n((?:\s*-\s*\S.*\n)*)")
LIST_ITEM_RE = re.compile(r'-\s*["\']?([A-Za-z0-9_.\-/]+)["\']?')


def _extract_depends_on(skill_md_path: Path) -> list[str]:
    text = skill_md_path.read_text()
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


class SkillMetadataTests(unittest.TestCase):
    def test_target_skill_directories_exist_with_skill_md(self):
        actual = {path.name for path in SKILLS_ROOT.iterdir() if path.is_dir()}
        self.assertEqual(EXPECTED_SKILLS - actual, set())
        for name in EXPECTED_SKILLS:
            self.assertTrue((SKILLS_ROOT / name / "SKILL.md").is_file())

    def test_depends_on_references_resolve(self):
        broken = []
        for name in EXPECTED_SKILLS:
            for dep in _extract_depends_on(SKILLS_ROOT / name / "SKILL.md"):
                if dep not in EXPECTED_SKILLS:
                    broken.append((name, dep))
        self.assertEqual(broken, [])


if __name__ == "__main__":
    unittest.main()
