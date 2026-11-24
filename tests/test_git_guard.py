#!/usr/bin/env python3
"""Tests for hooks/git_guard.py."""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from hook_test_support import HookCase, fixture  # noqa: E402


class GitGuard:
    cases = fixture("git-guard.json")

    @staticmethod
    def expect(test, case, reason):
        for rule in case["rules"]:
            test.assertIn(f"[{rule}]", reason)
        test.assertIn("Safe:", reason)


class GitGuardTests(HookCase):
    def decide(self, case, script="git_guard.py"):
        return self.bash(script, case["command"], case["cwd"])

    def test_incident_replays_are_denied_naming_rule_and_alternative(self):
        for case in GitGuard.cases["deny"]:
            with self.subTest(case["name"]):
                GitGuard.expect(self, case, self.denied(self.decide(case)))

    def test_legitimate_neighbours_pass(self):
        for case in GitGuard.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case))

    def test_override_is_logged(self):
        case = next(c for c in GitGuard.cases["allow"] if c["name"] == "logged override")
        self.decide(case)
        log = (self.tmp / "state" / "guard.log").read_text()
        self.assertIn("owner asked to reset main", log)
        self.assertIn("reset --hard origin/main", log)

    def test_without_checkouts_only_the_rules_for_everywhere_apply(self):
        self.settings({})
        self.assertIsNone(self.bash("git_guard.py", "git reset --hard a780eb7b", "{home}/app"))
        self.assertIsNone(self.bash("git_guard.py", "git push origin main", "{home}/app"))
        self.assertIn("[stash]", self.denied(self.bash("git_guard.py", "git stash", "{home}/app")))
        reason = self.denied(self.bash("git_guard.py", "git worktree add ../app-outside", "{home}/app"))
        self.assertIn("[worktree-location]", reason)
        self.assertIn("junkfather own --kind worktree", reason)

    def test_env_replaces_the_configured_checkouts(self):
        self.env["MASTACK_HOOK_REPOS"] = str(self.tmp / "other")
        self.assertIsNone(self.bash("git_guard.py", "git reset --hard a780eb7b", "{home}/app"))
        self.assertIn("[shared-checkout]", self.denied(self.bash("git_guard.py", "git reset --hard x", str(self.tmp / "other"))))

    def test_shell_combined_c_flags_and_command_substitutions_are_denied(self):
        self.assertIn("[shared-checkout]",
                      self.denied(self.bash("git_guard.py", "zsh -lc 'git reset --hard'", "{home}/app")))
        self.assertIn("[shared-checkout]",
                      self.denied(self.bash("git_guard.py", "bash -c -- 'git reset --hard'", "{home}/app")))
        self.assertIn("[push-force]",
                      self.denied(self.bash("git_guard.py", "bash -norc -c 'git push --force origin feat'", "{home}/app")))
        self.assertIn("[shared-checkout]",
                      self.denied(self.bash("git_guard.py", 'cd {home}/app && echo "$(git reset --hard)" && cd /tmp', "/tmp")))
        self.assertIsNone(self.bash("git_guard.py", 'cd /tmp && echo "$(git reset --hard)" && cd {home}/app', "{home}/app"))
        self.assertIn("[stash]",
                      self.denied(self.bash("git_guard.py", 'echo "`git stash`"', "{home}/app")))

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("git_guard.py")


if __name__ == "__main__":
    unittest.main()
