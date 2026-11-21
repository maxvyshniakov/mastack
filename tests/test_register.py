#!/usr/bin/env python3
"""Tests for hooks/register.py."""
from __future__ import annotations

import json
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from hook_test_support import HookCase  # noqa: E402


class RegisterTests(HookCase):
    """What tests/install_test.sh cannot stage: Claude Code writing the settings while the installer runs."""

    def test_the_rules_lifecycle_entries_ask_for_are_added_recorded_and_removed(self):
        import register
        rule = "Bash(/opt/tool background:*)"
        self.settings({"lifecycle": {"PreToolUse": [{"command": "/opt/tool hook", "rewrite": True,
                                                     "allow": [rule, rule]}]}})
        self.assertEqual([rule], register.lifecycle_allow(self.config))
        mine = {"permissions": {"allow": ["Bash(ls:*)"]}, "model": "kept"}
        report, claimed = [], []
        added = register.updated(mine, False, set(), report, (), False, [rule], set(), claimed)
        self.assertEqual(["Bash(ls:*)", rule], added["permissions"]["allow"])
        self.assertEqual(([rule], [f"add    permission: {rule}"]), (claimed, [r for r in report if "permission" in r]))
        again = register.updated(added, False, set(), [], (), False, [rule], {rule}, claimed)
        self.assertEqual((added["permissions"], [rule]), (again["permissions"], claimed), "once")
        gone = register.updated(again, False, set(), [], (), False, [], {rule}, claimed)
        self.assertEqual((["Bash(ls:*)"], []), (gone["permissions"]["allow"], claimed),
                         "no entry asks for it any more")
        theirs = register.updated(mine, False, set(), [], (), False, ["Bash(ls:*)"], set(), claimed)
        self.assertEqual(([], ["Bash(ls:*)"]), (claimed, theirs["permissions"]["allow"]),
                         "a rule that was there before is not claimed")
        removed = register.updated(again, True, set(), [], (), False, [rule], {rule}, claimed)
        self.assertEqual(["Bash(ls:*)"], removed["permissions"]["allow"], "uninstall removes only its own")
        self.assertEqual("kept", removed["model"])
        with self.assertRaises(register.Refused):
            register.updated({"permissions": {"allow": "Bash"}}, False, set(), [], (), False, [rule], set(), [])

    def test_a_handler_an_entry_replaces_is_removed(self):
        import register
        old = "sh -c 'exec \"$0\" hook' /opt/tool"
        self.settings({"lifecycle": {"PreToolUse": [{"command": "/opt/tool hook", "rewrite": True,
                                                     "replaces": [old]}]}})
        self.assertEqual({old}, register.lifecycle_replaces(self.config))
        theirs = {"type": "command", "command": "other hook"}
        settings = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": old}]},
                                             {"matcher": "Bash", "hooks": [theirs]}]}}
        result = register.updated(settings, False, set(), [], (), False, replaces={old})
        commands = [h["command"] for g in result["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertNotIn(old, commands)
        self.assertIn("other hook", commands)

    def test_install_records_the_rules_it_added(self):
        import register
        rule = "Bash(/opt/tool background:*)"
        self.settings({"lifecycle": {"PreToolUse": [{"command": "/opt/tool hook", "rewrite": True, "allow": [rule]}]}})
        settings = self.tmp / "settings.json"
        argv = ["register.py", "--settings", str(settings), "--config", str(self.config), "--from-worktree"]
        with mock.patch.object(sys, "argv", argv), mock.patch("sys.stdout"):
            self.assertEqual(register.main(), 0)
        self.assertEqual([rule], json.loads(settings.read_text())["permissions"]["allow"])
        self.assertEqual([rule], register.recorded_allow(self.config))
        with mock.patch.object(sys, "argv", argv + ["--uninstall"]), mock.patch("sys.stdout"):
            self.assertEqual(register.main(), 0)
        self.assertNotIn("permissions", json.loads(settings.read_text()))

    def test_a_concurrent_write_is_kept_and_the_install_retried(self):
        import register
        settings = self.tmp / "settings.json"
        settings.write_text(json.dumps({"model": "a"}, indent=2) + "\n")
        real_render, calls = register.render, []

        def render(data, ascii_only):
            calls.append(1)
            if len(calls) == 1:  # Claude Code saves a change between our read and our write
                settings.write_text(json.dumps({"model": "a", "theme": "dark"}, indent=2) + "\n")
            return real_render(data, ascii_only)

        argv = ["register.py", "--settings", str(settings), "--config", str(self.config), "--from-worktree"]
        with mock.patch.object(register, "render", side_effect=render), mock.patch.object(sys, "argv", argv), \
                mock.patch("sys.stdout") as out:
            self.assertEqual(register.main(), 0)
        result = json.loads(settings.read_text())
        self.assertEqual(result["theme"], "dark", "the concurrent change survives")
        self.assertEqual([h["command"] for g in result["hooks"]["PreToolUse"] for h in g["hooks"]],
                         [register.command(), register.agent_role_command()])
        self.assertEqual(len(calls), 2)
        self.assertIn("retry", "".join(str(call) for call in out.write.call_args_list))


if __name__ == "__main__":
    unittest.main()
