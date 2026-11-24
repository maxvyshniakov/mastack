#!/usr/bin/env python3
"""Tests for hooks/release_guard.py."""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from hook_test_support import HookCase, PROJECT_STEPS, fixture  # noqa: E402


class ReleaseGuardTests(HookCase):
    """Releases and publishes are refused without a matching MASTACK_RELEASE_OK in the environment."""

    cases = fixture("release-guard.json")

    def setUp(self):
        super().setUp()
        self.env.pop("CLAUDE_CODE_ENTRYPOINT", None)
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


class StandingPermissionTests(HookCase):
    """A routine patch or minor of a declared package passes without a go-ahead; the rest is the owner's call."""

    def setUp(self):
        super().setUp()
        self.env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        self.env.update(GIT_CONFIG_GLOBAL=str(self.tmp / "gitconfig"), GIT_CONFIG_NOSYSTEM="1")
        self.repo = self.home / "grid"
        self.pkg = self.repo / "packages" / "grid"
        self.pkg.mkdir(parents=True)

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
                        "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
                       check=True, capture_output=True, env=self.env)

    def write(self, version, changelog="", publish_config=None):
        data = {"name": "@acme/grid", "version": version}
        if publish_config is not None:
            data["publishConfig"] = publish_config
        (self.pkg / "package.json").write_text(json.dumps(data))
        (self.pkg / "CHANGELOG.md").write_text(
            f"# Changelog\n\n## Unreleased\n\n{changelog}\n## {version} - 2026-11-24\n\n{changelog or '- Fixed: x.'}\n\n"
            "## 0.0.1 - 2026-01-01\n\n- Breaking: old.\n")

    def make(self, previous="1.2.0", target="1.2.1", changelog="", declared=("@acme/grid",), tag=True,
             publish_config=None, levels=None):
        """A repository whose last tag is `previous` and whose packages/grid is at `target`, committed on origin/main
        with a `release_standing` that declares `declared` (None: no declaration)."""
        (self.repo / "package.json").write_text(json.dumps({"name": "grid-workspace", "private": True}))
        (self.repo / "docs" / "agents").mkdir(parents=True, exist_ok=True)
        hooks = {} if declared is None else {"release_standing": {"packages": list(declared),
                                                                   **({"levels": levels} if levels else {})}}
        (self.repo / "docs" / "agents" / "hooks.json").write_text(json.dumps(hooks))
        shutil.rmtree(self.repo / ".git", ignore_errors=True)
        self.git("init", "-q", "-b", "main")
        self.write(previous, publish_config=publish_config)
        self.git("add", "-A")
        self.git("commit", "-qm", "previous")
        if tag:
            self.git("tag", f"v{previous}")
        self.write(target, changelog, publish_config)
        self.git("commit", "-q", "--allow-empty", "-am", "release")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def decide(self, command, cwd="{home}/grid", script="release_guard.py", entrypoint=None, **payload):
        saved = dict(self.env)
        try:
            if entrypoint:
                self.env["CLAUDE_CODE_ENTRYPOINT"] = entrypoint
            for key in [k for k in payload if k.startswith("MASTACK_")]:
                self.env[key] = payload.pop(key)
            return self.bash(script, command, cwd, **payload)
        finally:
            self.env = saved

    def refused(self, command, fact, **kwargs):
        reason = self.denied(self.decide(command, **kwargs))
        self.assertIn(fact, reason)
        self.assertIn("stop with the release ready", reason)
        return reason

    def test_patch_passes(self):
        self.make("1.2.0", "1.2.1")
        for command in ("bun run release:publish", "npm publish", "git push origin v1.2.1",
                        "gh release create v1.2.1 --generate-notes", "gh workflow run release-npm.yml --ref main",
                        "lanefather promote HEAD --ship"):
            with self.subTest(command):
                self.assertIsNone(self.decide(command))
                self.assertIsNone(self.decide(command, script="bash_guard.py"))
        self.assertIsNone(self.decide("npm publish", cwd="{home}/grid/packages/grid"))

    def test_minor_passes_also_before_one_when_not_breaking(self):
        for previous, target in (("1.2.0", "1.3.0"), ("0.4.1", "0.5.0")):
            with self.subTest(target):
                self.make(previous, target)
                self.assertIsNone(self.decide("bun run release:publish"))

    def test_cutting_a_patch_or_minor_passes_and_a_major_is_refused(self):
        self.make("1.2.0", "1.2.0")
        self.assertIsNone(self.decide("bun run release -- grid:patch"))
        self.assertIsNone(self.decide("bun run release -- minor"))
        self.refused("bun run release -- grid:major", "major step")
        self.refused("bun run release -- @acme/grid:2.0.0", "major step")

    def test_major_is_refused(self):
        self.make("1.2.0", "2.0.0")
        for command in ("bun run release:publish", "git push origin v2.0.0", "gh workflow run release-npm.yml"):
            with self.subTest(command):
                self.refused(command, "1.2.0 -> 2.0.0 is a major step")

    def test_breaking_entry_is_refused_even_as_a_pre_one_minor(self):
        self.make("0.4.1", "0.5.0", changelog="### Breaking\n\n- Breaking: renamed `x`.\n")
        self.refused("bun run release:publish", "has a Breaking entry")
        self.refused("bun run release -- grid:minor", "`## Unreleased` of @acme/grid has a Breaking entry")

    def test_declared_levels_narrow_the_permission(self):
        self.make("1.2.0", "1.3.0", levels=["patch"])
        self.refused("bun run release:publish", "is a minor step; the standing permission covers patch")

    def test_first_publication_is_refused(self):
        self.make("1.2.0", "1.2.1", tag=False)
        self.refused("bun run release:publish", "first publication of @acme/grid")

    def test_visibility_and_access_changes_are_refused(self):
        self.make("1.2.0", "1.2.1")
        for command, fact in (
            ("gh repo edit --visibility public --accept-visibility-change-consequences", "visibility"),
            ("gh repo create acme/new --public", "public repository"),
            ("gh api -X POST repos/acme/grid/pages -f build_type=workflow", "Pages"),
            ("npm access set status=public @acme/grid", "access"),
            ("npm publish --access public", "`--access public` changes how @acme/grid is published"),
        ):
            with self.subTest(command):
                self.refused(command, fact)
        for command in ("gh repo edit --visibility public", "npm access set status=public @acme/grid"):
            with self.subTest(command, granted=True):  # owner-only: the variable does not cover them
                self.refused(command, "owner's command each time", MASTACK_RELEASE_OK="@acme/grid@1.2.1")
        self.assertIsNone(self.decide("gh api repos/acme/grid/pages"))
        self.assertIsNone(self.decide("npm access get status @acme/grid"))

    def test_access_already_public_passes(self):
        self.make("1.2.0", "1.2.1", publish_config={"access": "public"})
        self.assertIsNone(self.decide("npm publish --access public"))

    def test_undeclared_project_or_package_is_refused(self):
        self.make("1.2.0", "1.2.1", declared=None)
        self.refused("bun run release:publish", "no standing permission")
        self.make("1.2.0", "1.2.1", declared=("@acme/other",))
        self.refused("bun run release:publish", "@acme/grid not declared under `release_standing`")

    def test_an_unlanded_declaration_does_not_count(self):
        self.make("1.2.0", "1.2.1", declared=None)
        (self.repo / "docs" / "agents" / "hooks.json").write_text(
            json.dumps({"release_standing": {"packages": ["@acme/grid"]}}))
        self.git("commit", "-qam", "opt in on a lane")
        self.refused("bun run release:publish", "no standing permission")

    def test_unparseable_version_is_refused(self):
        self.make("1.2.0", "1.3.0-beta.1")
        self.refused("bun run release:publish", "cannot read a plain x.y.z version")
        self.refused("git push origin --tags", "cannot read a plain vX.Y.Z tag")

    def test_ship_of_another_commit_is_refused(self):
        self.make("1.2.0", "1.2.1")
        self.refused("lanefather promote d52ab67d --ship", "is not this checkout's HEAD")

    def test_outside_a_repository_is_refused(self):
        self.refused("npm publish", "not inside a Git repository", cwd=str(self.tmp))

    def test_variable_path_still_grants_what_the_standing_permission_does_not(self):
        self.make("1.2.0", "2.0.0")
        self.assertIsNone(self.decide("bun run release:publish", MASTACK_RELEASE_OK="@acme/grid@2.0.0"))
        self.refused("bun run release:publish", "major step", MASTACK_RELEASE_OK="@acme/grid@2.1.0")

    def test_card_only_where_it_reaches_the_owner(self):
        self.make("1.2.0", "2.0.0")
        for mode in ("default", "acceptEdits", "bypassPermissions"):
            with self.subTest(mode):
                for script in ("release_guard.py", "bash_guard.py"):
                    output = self.decide("bun run release:publish", script=script, entrypoint="t3-code",
                                         permission_mode=mode)
                    decision = output["hookSpecificOutput"]
                    self.assertEqual(decision["permissionDecision"], "ask")
                    self.assertIn("`bun run release:publish`", decision["permissionDecisionReason"])
                    self.assertIn("1.2.0 -> 2.0.0 is a major step", decision["permissionDecisionReason"])
        # Where `ask` is auto-approved or unproven: deny.
        for entrypoint, payload in (("t3-code", {"permission_mode": "auto"}),
                                    ("t3-code", {"permission_mode": "dontAsk"}),
                                    ("t3-code", {"permission_mode": "plan"}),
                                    ("t3-code", {"permission_mode": "bypassPermissions", "turn_id": "t1"}),
                                    ("claude-desktop", {"permission_mode": "default"}),
                                    ("cli", {"permission_mode": "default"}),
                                    ("sdk-cli", {"permission_mode": "bypassPermissions"}),
                                    (None, {"permission_mode": "default"})):
            with self.subTest(entrypoint=entrypoint, **payload):
                self.refused("bun run release:publish", "major step", entrypoint=entrypoint, **payload)

    def test_a_self_granted_variable_gets_no_card(self):
        self.make("1.2.0", "2.0.0")
        reason = self.denied(self.decide("MASTACK_RELEASE_OK=@acme/grid@2.0.0 bun run release:publish",
                                         entrypoint="t3-code", permission_mode="bypassPermissions"))
        self.assertIn("inside the command itself does not count", reason)


if __name__ == "__main__":
    unittest.main()
