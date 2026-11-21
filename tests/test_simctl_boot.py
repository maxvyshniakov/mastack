#!/usr/bin/env python3
"""Tests for hooks/simctl_boot.py."""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from hook_test_support import HookCase, fixture  # noqa: E402


class SimctlBootTests(HookCase):
    """A simulator boot must run under `junkfather own --kind simulator`; a stand-in junkfather marks it installed
    (the check only looks for it, never runs it)."""

    cases = fixture("simctl-boot.json")

    def stand_in(self):
        fake = self.tmp / "junkfather"
        if not fake.exists():
            fake.write_text("#!/bin/sh\nexit 1\n")
            fake.chmod(0o755)
        self.env["MASTACK_JUNKFATHER"] = str(fake)

    def decide(self, command, script="simctl_boot.py"):
        if "MASTACK_JUNKFATHER" not in self.env:
            self.stand_in()
        return self.bash(script, command, "{home}/app")

    @staticmethod
    def expect(test, case, reason):
        test.assertIn("simctl-boot denied", reason)
        test.assertIn(case["says"], reason)
        test.assertIn(test.fill(case["run"]), reason)
        test.assertIn("junkfather own --kind simulator [--ttl 2h] [--label L] -- xcrun simctl boot <udid>", reason)

    def test_boots_outside_junkfather_are_denied_with_the_wrapped_form(self):
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.expect(self, case, self.denied(self.decide(case["command"])))

    def test_owned_boots_and_other_subcommands_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"]))

    def test_without_junkfather_every_boot_passes(self):
        self.env["MASTACK_JUNKFATHER"] = str(self.tmp / "missing-junkfather")
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"]))
        self.env.pop("MASTACK_JUNKFATHER")
        self.env["PATH"] = "/usr/bin:/bin"
        self.assertIsNone(self.bash("simctl_boot.py", "xcrun simctl boot $UDID", "{home}/app"))

    def test_unreadable_or_empty_input_passes(self):
        self.stand_in()
        self.assertFailsOpen("simctl_boot.py")


if __name__ == "__main__":
    unittest.main()
