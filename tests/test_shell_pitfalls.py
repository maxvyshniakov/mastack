#!/usr/bin/env python3
"""Tests for hooks/shell_pitfalls.py."""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from hook_test_support import HookCase, fixture  # noqa: E402


class ShellPitfallsTests(HookCase):
    cases = fixture("shell-pitfalls.json")

    def decide(self, command, script="shell_pitfalls.py"):
        return self.bash(script, command, "{home}")

    @staticmethod
    def expect(test, case, reason):
        test.assertIn(case["says"], reason)

    def test_gnu_forms_are_denied_naming_the_macos_form(self):
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.expect(self, case, self.denied(self.decide(case["command"])))

    def test_look_alikes_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"]))

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("shell_pitfalls.py")


if __name__ == "__main__":
    unittest.main()
