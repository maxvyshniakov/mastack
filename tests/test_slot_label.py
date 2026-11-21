#!/usr/bin/env python3
"""Tests for hooks/slot_label.py."""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from hook_test_support import HookCase, fixture  # noqa: E402


class SlotLabelTests(HookCase):
    cases = fixture("slot-label.json")

    def decide(self, case, script="slot_label.py"):
        return self.bash(script, case["command"], case.get("cwd", "{home}/app"))

    @staticmethod
    def expect(test, case, reason):
        test.assertIn(case["says"], reason)
        test.assertIn(case["example"], reason)
        test.assertIn("<task or ticket> <what it does>", reason)
        test.assertIn("everyone reads labels on the slotfather dashboard", reason)

    def test_missing_directory_and_generic_labels_are_denied_with_an_example(self):
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.expect(self, case, self.denied(self.decide(case)))

    def test_meaningful_labels_and_wrappers_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case))

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("slot_label.py")
        self.assertIsNone(self.decide({"command": "slotfather run -n 1 -- echo \"unterminated"}))


if __name__ == "__main__":
    unittest.main()
