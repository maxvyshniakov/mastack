#!/usr/bin/env python3
"""Mechanical pack invariants: skill metadata, frontmatter, links, line budget, doc sync, models.toml order."""
from __future__ import annotations

import pathlib
import re
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
MAX_SKILL_LINES = 200
REPO_ISSUE_RE = re.compile(r"(?<!UPSTREAM\()(?<![\w/])(?!owner/|acme/)(?:[A-Za-z0-9._-]+/)?[A-Za-z0-9._-]+#\d+\b")
GITHUB_ISSUE_URL_RE = re.compile(r"https?://github\.com/(?!owner/|acme/)[^/\s]+/[^/\s]+/issues/\d+")
MD_LINK_RE = re.compile(r"\]\(([^)#]+)(?:#[^)]+)?\)")


class SkillLintTests(unittest.TestCase):
    def skills(self) -> list[pathlib.Path]:
        return sorted(p.parent for p in SKILLS_DIR.glob("*/SKILL.md"))

    def test_every_skill_has_valid_frontmatter_openai_yaml_and_line_budget(self):
        for skill in self.skills():
            with self.subTest(skill.name):
                yaml_path = skill / "agents" / "openai.yaml"
                self.assertTrue(yaml_path.is_file(), f"missing {yaml_path.relative_to(ROOT)}")
                yaml_text = yaml_path.read_text()
                self.assertIn("display_name:", yaml_text)
                self.assertIn("short_description:", yaml_text)
                text = (skill / "SKILL.md").read_text()
                lines = text.splitlines()
                self.assertLessEqual(len(lines), MAX_SKILL_LINES,
                                     f"{skill.name}/SKILL.md has {len(lines)} lines (limit {MAX_SKILL_LINES})")
                self.assertTrue(text.startswith("---\n"), f"{skill.name}/SKILL.md missing YAML frontmatter")
                front = text.split("---\n", 2)[1]
                self.assertRegex(front, rf"(?m)^name:\s*{re.escape(skill.name)}\s*$")
                self.assertRegex(front, r"(?m)^description:\s*\S+")

    def test_local_markdown_links_inside_skills_resolve(self):
        for path in sorted(SKILLS_DIR.rglob("*.md")):
            text = path.read_text()
            for target in MD_LINK_RE.findall(text):
                if target.startswith(("http://", "https://", "mailto:", "<")):
                    continue
                resolved = (path.parent / target).resolve()
                self.assertTrue(resolved.exists(), f"{path.relative_to(ROOT)} broken link -> {target}")

    def test_readme_skills_table_matches_skills_directory(self):
        readme = (ROOT / "README.md").read_text()
        linked = set(re.findall(r"\]\(skills/([^/]+)/SKILL\.md\)", readme))
        actual = {s.name for s in self.skills()}
        self.assertEqual(linked, actual, f"README drift: extra={linked - actual}, missing={actual - linked}")

    def test_skills_do_not_leak_raw_issue_refs_or_urls(self):
        for path in sorted(SKILLS_DIR.rglob("*.md")):
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                if "check:allow" in line or "UPSTREAM(" in line:
                    continue
                self.assertIsNone(REPO_ISSUE_RE.search(line), f"{path.relative_to(ROOT)}:{lineno}: raw issue ref")
                self.assertIsNone(GITHUB_ISSUE_URL_RE.search(line), f"{path.relative_to(ROOT)}:{lineno}: raw issue URL")

    def test_models_toml_review_cross_family_precedes_same_family_fallback(self):
        table = tomllib.loads((ROOT / "models.toml").read_text())
        seen_unconditional = False
        for choice in table["roles"]["review"]["choices"]:
            when = choice.get("when") or {}
            if when.get("not_family"):
                self.assertFalse(seen_unconditional,
                                 f"not_family choice {choice['model']} appears below unconditional fallback")
            elif not when:
                seen_unconditional = True

    def test_models_md_names_every_model_used_in_roles(self):
        table = tomllib.loads((ROOT / "models.toml").read_text())
        models_md = (ROOT / "models.md").read_text().lower()
        used = {choice["model"].lower() for role in table["roles"].values() for choice in role["choices"]}
        for alias in sorted(used):
            with self.subTest(alias=alias):
                self.assertIn(alias, models_md, f"model {alias!r} used in models.toml is missing from models.md")


if __name__ == "__main__":
    unittest.main()
