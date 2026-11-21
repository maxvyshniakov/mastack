#!/usr/bin/env python3
"""Tests for hooks/release_guard.py."""
from __future__ import annotations

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from hook_test_support import HookCase, PROJECT_STEPS, fixture  # noqa: E402


class ReleaseGuardTests(HookCase):
    """Releases and publishes are refused without a matching MASTACK_RELEASE_OK in the environment."""

    cases = fixture("release-guard.json")

    def setUp(self):
        super().setUp()
        (self.project / "package.json").write_text(json.dumps({"name": "@acme/ui-kit", "version": "1.2.0"}))

    def decide(self, command, script="release_guard.py", cwd="{home}/app", **extra_env):
        saved = dict(self.env)
        try:
            self.env.update(extra_env)
            return self.bash(script, command, cwd)
        finally:
            self.env = saved

    @staticmethod
    def expect(test, case, reason):
        test.assertIn("release-guard denied", reason)
        test.assertIn("MASTACK_RELEASE_OK=<package>@<version>", reason)
        test.assertIn("Only the owner can grant it", reason)
        test.assertIn("never set `MASTACK_RELEASE_OK` themselves", reason)

    def test_releases_and_publishes_without_an_owner_go_ahead_are_denied(self):
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.expect(self, case, self.denied(self.decide(case["command"])))

    def test_non_release_commands_and_dry_runs_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"]))

    def test_each_command_shape_passes_only_with_a_matching_go_ahead_in_the_environment(self):
        shapes = [
            ("npm publish", "@acme/ui-kit@1.2.0", "@acme/ui-kit@1.2.1"),
            ("bun publish", "@acme/ui-kit@1.2.0", "@acme/other@1.2.0"),
            ("pnpm publish", "ui-kit@1.2.0", "ui-kit@2.0.0"),
            ("yarn npm publish", "@acme/ui-kit@1.2.0", "1.2.0"),
            ("bun run release:publish", "@acme/ui-kit@1.2.0", "@acme/ui-kit@1.1.9"),
            ("repo-kit release -- ui-kit:patch", "@acme/ui-kit@1.2.1", "@acme/other@1.2.1"),
            ("repo-kit release ui-kit:1.3.0", "ui-kit@1.3.0", "ui-kit@1.2.0"),
            ("gh release create v1.2.0 --generate-notes", "v1.2.0", "v1.2.1"),
            ("gh release create v1.2.0 --generate-notes", "@acme/ui-kit@1.2.0", "@acme/ui-kit@1.2.1"),
            ("git push origin v1.2.0", "v1.2.0", "v1.2.1"),
            ("git push origin d52ab67d:refs/tags/v0.6.0", "repo-kit@0.6.0", "repo-kit@0.6.1"),
            ("lanefather promote d52ab67d --ship", "ship", "not-a-valid-token!"),
            ("lanefather promote d52ab67d --ship", "@acme/ui-kit@1.2.0", "other/bad/token"),
            ("sh -c 'bun run release:publish && git push origin v1.2.0'", "@acme/ui-kit@1.2.0", "ui-kit@1.2.1"),
        ]
        for command, matching, wrong in shapes:
            with self.subTest(command=command):
                self.assertIsNone(self.decide(command, MASTACK_RELEASE_OK=matching))
                self.assertIsNone(self.decide(command, script="bash_guard.py", MASTACK_RELEASE_OK=matching))
                self.denied(self.decide(command, MASTACK_RELEASE_OK=wrong))

    def test_inline_go_ahead_is_refused_even_when_environment_also_has_it(self):
        for command in (
            "MASTACK_RELEASE_OK=@acme/ui-kit@1.2.0 npm publish",
            "env MASTACK_RELEASE_OK=@acme/ui-kit@1.2.0 bun run release:publish",
            "export MASTACK_RELEASE_OK=@acme/ui-kit@1.2.0; bun publish",
            "sh -c 'MASTACK_RELEASE_OK=@acme/ui-kit@1.2.0 npm publish'",
        ):
            with self.subTest(command=command):
                reason = self.denied(self.decide(command, MASTACK_RELEASE_OK="@acme/ui-kit@1.2.0"))
                self.assertIn("Setting `MASTACK_RELEASE_OK` inside the command itself does not count", reason)

    def test_declared_lanefather_wrapper_promote_ship_is_guarded(self):
        (self.project / "docs" / "agents" / "hooks.json").write_text(
            json.dumps({"mutating_steps": PROJECT_STEPS, "lanefather_commands": ["tools/lane"]}))
        self.denied(self.decide("tools/lane --config /tmp/p.toml promote d52ab67d --ship"))
        self.assertIsNone(self.decide("tools/lane --config /tmp/p.toml promote d52ab67d"))
        self.assertIsNone(self.decide("tools/lane --config /tmp/p.toml promote d52ab67d --ship",
                                      MASTACK_RELEASE_OK="ship"))

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("release_guard.py")
        self.assertIsNone(self.decide("npm publish \"unterminated"))


if __name__ == "__main__":
    unittest.main()
