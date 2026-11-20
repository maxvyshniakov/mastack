#!/usr/bin/env python3
"""Tests for hooks/agent_role.py: filling missing model and effort on Agent launches from models.toml.

Runs as Claude Code runs PreToolUse hooks (JSON on stdin, updatedInput JSON on stdout, exit 0) in a scratch
environment; nothing reads the real settings or state.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"
TABLE = tomllib.loads((ROOT / "models.toml").read_text(encoding="utf-8"))
sys.path.insert(0, str(HOOKS))

import agent_role  # noqa: E402
import register  # noqa: E402


def model_id(name: str) -> str:
    return TABLE["models"][name]["id"]


class AgentRoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="mastack-agent-role-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.config = self.tmp / "config"
        self.config.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("MASTACK_")}
        self.env.update(HOME=str(self.tmp), MASTACK_CONFIG=str(self.config), MASTACK_HOOK_STATE=str(self.tmp / "state"))

    def run_hook(self, payload: dict | str, **extra_env: str) -> dict | None:
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        proc = subprocess.run([sys.executable, str(HOOKS / "agent_role.py")], input=stdin, capture_output=True,
                              text=True, env={**self.env, **extra_env}, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout) if proc.stdout.strip() else None

    def launch(self, tool_input: dict, **extra_env: str) -> dict | None:
        return self.run_hook({"hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": tool_input},
                             **extra_env)

    def test_fills_missing_model_and_effort_from_prompt_role_marker(self):
        out = self.launch({"description": "Build lane alpha", "prompt": "Role: implement\nTickets: acme/app#1\n"})
        self.assertIsNotNone(out)
        updated = out["hookSpecificOutput"]["updatedInput"]
        self.assertEqual(updated["model"], model_id("opus"))
        self.assertEqual(updated["effort"], "medium")
        self.assertEqual(updated["description"], "Build lane alpha")
        self.assertNotIn("permissionDecision", out["hookSpecificOutput"])

    def test_fills_design_scout_and_review_roles_with_claude_choices(self):
        cases = [
            ("[role: design] Architecture plan", "Plan the API", model_id("fable"), "high"),
            ("scout: find callers of parse()", "List call sites", model_id("sonnet"), "medium"),
            ("Review lane beta", "Check diff", model_id("opus"), "medium"),
            ("implementer: fix-lane alpha", "Fix findings", model_id("opus"), "medium"),
        ]
        for description, prompt, expected_model, expected_effort in cases:
            with self.subTest(description=description):
                out = self.launch({"description": description, "prompt": prompt})
                self.assertIsNotNone(out)
                updated = out["hookSpecificOutput"]["updatedInput"]
                self.assertEqual((updated["model"], updated["effort"]), (expected_model, expected_effort))

    def test_explicit_prompt_markers_apply_aliases_and_prefer_earliest_match(self):
        cases = [
            ("Build lane", "Role: implementer\nTickets: acme/app#1", model_id("opus"), "medium"),
            ("Check diff", "[role: reviewer] Inspect changes", model_id("opus"), "medium"),
            ("Fix parser", "Role: implement\nNote: fix how [role: scout] is parsed", model_id("opus"), "medium"),
            ("Plan API", "[role: design]\nRole: implement", model_id("fable"), "high"),
        ]
        for description, prompt, expected_model, expected_effort in cases:
            with self.subTest(prompt=prompt):
                out = self.launch({"description": description, "prompt": prompt})
                self.assertIsNotNone(out)
                updated = out["hookSpecificOutput"]["updatedInput"]
                self.assertEqual((updated["model"], updated["effort"]), (expected_model, expected_effort))

    def test_fills_only_the_missing_field_and_preserves_explicit_values(self):
        only_model = self.launch({"description": "implement lane a", "prompt": "Do work", "model": "sonnet"})
        self.assertIsNotNone(only_model)
        self.assertEqual(only_model["hookSpecificOutput"]["updatedInput"]["model"], "sonnet")
        self.assertEqual(only_model["hookSpecificOutput"]["updatedInput"]["effort"], "medium")

        only_effort = self.launch({"description": "design api", "prompt": "Plan", "effort": "medium"})
        self.assertIsNotNone(only_effort)
        self.assertEqual(only_effort["hookSpecificOutput"]["updatedInput"]["model"], model_id("fable"))
        self.assertEqual(only_effort["hookSpecificOutput"]["updatedInput"]["effort"], "medium")

        both = self.launch({"description": "implement lane a", "prompt": "Role: implement",
                            "model": model_id("opus"), "effort": "medium"})
        self.assertIsNone(both, "when model and effort are already set, no rewrite is emitted")

    def test_passes_through_without_a_known_role(self):
        for tool_input in (
            {"description": "Check git status", "prompt": "Run git status"},
            {"description": "custom: something", "prompt": "Role: unknown_role\nDo something"},
            {"description": "", "prompt": ""},
        ):
            with self.subTest(tool_input=tool_input):
                self.assertIsNone(self.launch(tool_input))

    def test_fails_open_on_other_tools_malformed_json_and_bad_table(self):
        self.assertIsNone(self.run_hook("not json"))
        self.assertIsNone(self.run_hook({"tool_name": "Bash", "tool_input": {"command": "echo Role: implement"}}))
        self.assertIsNone(self.run_hook({"tool_name": "Agent", "tool_input": "not a dict"}))
        self.assertIsNone(self.launch({"description": "implement x", "prompt": "Role: implement"},
                                      MASTACK_MODELS=str(self.tmp / "missing.toml")))

    def test_respects_custom_models_table(self):
        custom = self.tmp / "custom.toml"
        custom.write_text(
            'schema = 1\n'
            '[models.custom]\nid = "claude-custom-1"\nfamily = "anthropic"\ncli = "claude"\n'
            '[roles.implement]\nchoices = [{ model = "custom", effort = "low" }]\n',
            encoding="utf-8",
        )
        out = self.launch({"description": "lane x", "prompt": "Role: implement"}, MASTACK_MODELS=str(custom))
        self.assertIsNotNone(out)
        updated = out["hookSpecificOutput"]["updatedInput"]
        self.assertEqual((updated["model"], updated["effort"]), ("claude-custom-1", "low"))

    def test_register_adds_updates_and_uninstalls_agent_hook_idempotently(self):
        ours = {register.command(), register.agent_role_command()}
        report: list[str] = []
        added = register.updated({}, False, ours, report)
        agent_groups = [g for g in added["hooks"]["PreToolUse"] if g.get("matcher") == "Agent"]
        self.assertEqual(agent_groups, [{"matcher": "Agent", "hooks": [register.agent_role_handler()]}])
        self.assertTrue(any("add    PreToolUse Agent:" in line for line in report))

        report2: list[str] = []
        again = register.updated(added, False, ours, report2)
        self.assertEqual(again, added)
        self.assertEqual(report2, [])

        kept = {"hooks": {"PreToolUse": [{"matcher": "Agent", "hooks": [{"type": "command", "command": "other-agent"}]}]}}
        merged = register.updated(kept, False, ours, [])
        removed = register.updated(merged, True, ours, [])
        self.assertEqual(removed["hooks"]["PreToolUse"], kept["hooks"]["PreToolUse"])


if __name__ == "__main__":
    unittest.main()
