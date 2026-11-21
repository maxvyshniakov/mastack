#!/usr/bin/env python3
"""Tests for hooks/docker_desktop.py."""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from hook_test_support import HookCase, fixture  # noqa: E402


class DockerDesktopTests(HookCase):
    cases = fixture("docker-desktop.json")

    def decide(self, command, script="docker_desktop.py"):
        return self.bash(script, command, "{home}/app")

    @staticmethod
    def expect(test, case, reason):
        test.assertIn("docker-desktop denied", reason)
        test.assertIn(case["says"], reason)
        for alternative in ("docker compose restart", "docker compose up -d --force-recreate", "docker info",
                            "open -gja Docker"):
            test.assertIn(alternative, reason)

    def test_quitting_killing_restarting_or_opening_in_front_is_denied_with_the_alternatives(self):
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.expect(self, case, self.denied(self.decide(case["command"])))

    def test_docker_cli_orbstack_hidden_start_and_looks_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"]))

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("docker_desktop.py")


if __name__ == "__main__":
    unittest.main()
