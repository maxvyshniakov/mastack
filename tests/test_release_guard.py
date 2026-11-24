#!/usr/bin/env python3
"""Tests for hooks/release_guard.py."""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from hook_test_support import HookCase, PROJECT_STEPS, fixture, hook_io_reset  # noqa: E402


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
        if case.get("owner_only"):
            # F9: the variable does not cover visibility, access or Pages, so the refusal does not offer it.
            test.assertIn("the owner's command each time", reason)
            test.assertNotIn("set `MASTACK_RELEASE_OK=", reason)
            return
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
            ("gh workflow run release-npm.yml --ref main", "@acme/ui-kit@1.2.0", "@acme/ui-kit@1.2.1"),  # F9
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

    def test_empty_input_passes_and_an_unreadable_release_is_refused(self):
        self.assertFailsOpen("release_guard.py")
        self.expect(self, {}, self.denied(self.decide("npm publish \"unterminated")))  # F5: was a pass
        self.assertIsNone(self.decide("echo \"unterminated"))


class StandingPermissionTests(HookCase):
    """A routine patch or minor of the one declared package passes without a go-ahead, but only for the plain release
    commands the projects document, run from the repository root, with facts read from the commit and the remote."""

    def setUp(self):
        super().setUp()
        self.env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        self.env.update(GIT_CONFIG_GLOBAL=str(self.tmp / "gitconfig"), GIT_CONFIG_NOSYSTEM="1")
        self.repo = self.home / "grid"
        self.pkg = self.repo / "packages" / "grid"
        self.remote = self.tmp / "remote.git"

    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-C", str(cwd or self.repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
                               "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
                              check=True, capture_output=True, text=True, env=self.env).stdout.strip()

    def write(self, version, changelog="", publish_config=None, heading=None):
        data = {"name": "@acme/grid", "version": version}
        if publish_config is not None:
            data["publishConfig"] = publish_config
        (self.pkg / "package.json").write_text(json.dumps(data))
        title = heading or f"## {version} - 2026-11-24"
        (self.pkg / "CHANGELOG.md").write_text(
            f"# Changelog\n\n## Unreleased\n\n{changelog}\n{title}\n\n{changelog or '- Fixed: x.'}\n\n"
            "## 0.0.1 - 2026-01-01\n\n- Breaking: old.\n")

    def make(self, previous="1.2.0", target="1.2.1", changelog="", declared=("@acme/grid",), tag=True,
             publish_config=None, levels=None, heading=None, push=True):
        """A clone whose remote holds `previous` tagged and `target` on main, with `release_standing` declaring
        `declared` (None: none) as committed on the remote's main."""
        for path in (self.repo, self.remote):
            shutil.rmtree(path, ignore_errors=True)
        self.pkg.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], check=True, env=self.env)
        (self.repo / "package.json").write_text(json.dumps({"name": "grid-workspace", "private": True}))
        (self.repo / "docs" / "agents").mkdir(parents=True, exist_ok=True)
        standing = {"packages": list(declared or ()), **({"levels": levels} if levels is not None else {})}
        hooks = {} if declared is None else {"release_standing": standing}
        (self.repo / "docs" / "agents" / "hooks.json").write_text(json.dumps(hooks))
        self.git("init", "-q", "-b", "main")
        self.git("remote", "add", "origin", str(self.remote))
        self.write(previous, publish_config=publish_config)
        self.git("add", "-A")
        self.git("commit", "-qm", "previous")
        if tag:
            self.git("tag", "-a", f"v{previous}", "-m", previous)
        self.write(target, changelog, publish_config, heading)
        self.git("commit", "-q", "--allow-empty", "-am", "release")
        if push:
            self.git("push", "-q", "origin", "main", "--tags")
        else:
            self.git("push", "-q", "origin", "HEAD~1:refs/heads/main", "--tags")
        self.git("fetch", "-q", "origin")
        return self.git("rev-parse", "HEAD")

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

    def passes(self, command, **kwargs):
        for script in ("release_guard.py", "bash_guard.py"):
            with self.subTest(command=command, script=script):
                self.assertIsNone(self.decide(command, script=script, **kwargs))

    def refused(self, command, fact, script="bash_guard.py", **kwargs):
        reason = self.denied(self.decide(command, script=script, **kwargs))
        self.assertIn(fact, reason)
        return reason

    # ---- the shapes that pass ------------------------------------------------------------------------------------

    def test_patch_passes_in_each_documented_shape(self):
        sha = self.make("1.2.0", "1.2.1")
        for command in ("bun run release:publish", "gh workflow run release-npm.yml --ref main",
                        f"lanefather promote {sha} --ship",
                        f"LANEFATHER_REVIEW_START=manual lanefather promote {sha} --ship"):
            self.passes(command)

    def test_minor_passes_also_before_one_when_not_breaking(self):
        for previous, target in (("1.2.0", "1.3.0"), ("0.4.1", "0.5.0")):
            self.make(previous, target)
            self.passes("bun run release:publish")

    def test_cutting_a_patch_or_minor_passes_and_a_major_is_refused(self):
        self.make("1.2.0", "1.2.0")
        self.passes("bun run release -- grid:patch")
        self.passes("bun run release -- minor")
        self.refused("bun run release -- grid:major", "major step")

    def test_a_ship_that_releases_no_new_version_passes(self):
        sha = self.make("1.2.0", "1.2.0")
        self.passes(f"lanefather promote {sha} --ship")

    # ---- the facts ------------------------------------------------------------------------------------------------

    def test_major_is_refused(self):
        sha = self.make("1.2.0", "2.0.0")
        for command in ("bun run release:publish", "gh workflow run release-npm.yml --ref main",
                        f"lanefather promote {sha} --ship"):
            self.refused(command, "1.2.0 -> 2.0.0 is a major step")

    def test_breaking_entries_are_refused_in_every_conventional_form(self):  # F8
        for entry in ("### Breaking\n\n- Breaking: renamed `x`.", "BREAKING CHANGE: dropped foo.",
                      "- Breaking change: dropped foo.", "- **Breaking**: dropped foo.", "#### Breaking\n\n- x.",
                      "### ⚠️ Breaking\n\n- x.", "- Breaking: renamed `x`."):
            with self.subTest(entry):
                self.make("0.4.1", "0.5.0", changelog=entry + "\n")
                self.refused("bun run release:publish", "Breaking entry")
                self.refused("bun run release -- grid:minor", "`## Unreleased` of @acme/grid has a Breaking entry")

    def test_a_word_ending_in_breaking_is_not_a_breaking_entry(self):  # F8
        self.make("1.2.0", "1.2.1", changelog="- Fixed: line-breaking: wrap on CJK.\n")
        self.passes("bun run release:publish")

    def test_linked_and_root_changelog_headings_are_found(self):  # F8
        self.make("1.2.0", "1.2.1", heading="## [1.2.1](https://example.com/compare/v1.2.0...v1.2.1) - 2026-11-24")
        self.passes("bun run release:publish")
        self.make("1.2.0", "1.2.1", heading="## 1.2.2 - 2026-11-24")
        self.refused("bun run release:publish", "no `## 1.2.1` section")

    def test_declared_levels_narrow_the_permission(self):  # F7
        self.make("1.2.0", "1.3.0", levels=["patch"])
        self.refused("bun run release:publish", "is a minor step; the standing permission covers patch")
        self.make("1.2.0", "1.2.1", levels=[])
        self.refused("bun run release:publish", "covers no level")
        self.make("1.2.0", "1.2.1", levels="none")
        self.refused("bun run release:publish", "covers no level")

    def test_first_publication_is_refused_and_a_local_tag_does_not_change_that(self):  # F1
        self.make("0.1.0", "0.1.0", tag=False)
        self.git("tag", "v0.0.0")
        self.refused("bun run release:publish", "first publication of @acme/grid")

    def test_a_tag_only_on_the_remote_or_only_local_does_not_count(self):  # F1
        self.make("1.2.0", "2.0.1")
        self.git("tag", "v2.0.0")
        self.refused("bun run release:publish", "1.2.0 -> 2.0.1 is a major step")

    def test_undeclared_project_or_package_is_refused(self):
        self.make("1.2.0", "1.2.1", declared=None)
        self.refused("bun run release:publish", "no standing permission")
        self.make("1.2.0", "1.2.1", declared=("@acme/other",))
        self.refused("bun run release:publish", "@acme/grid is not declared under `release_standing`")

    def test_a_local_origin_main_does_not_grant_the_permission(self):  # F1
        self.make("1.2.0", "1.2.1", declared=None)
        (self.repo / "docs" / "agents" / "hooks.json").write_text(
            json.dumps({"release_standing": {"packages": ["@acme/grid"]}}))
        self.git("checkout", "-qb", "origin/main")
        self.git("commit", "-qam", "opt in on a local branch named like the remote's")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("checkout", "-q", "main")
        self.refused("bun run release:publish", "no standing permission")

    def test_uncommitted_changes_are_refused(self):  # F1
        sha = self.make("1.2.0", "2.0.0")
        self.write("1.2.1")
        self.refused(f"lanefather promote {sha} --ship", "uncommitted changes")
        self.refused("bun run release:publish", "uncommitted changes")

    def test_publish_needs_head_to_be_the_remote_main(self):  # F1
        self.make("1.2.0", "1.2.1", push=False)
        self.refused("bun run release:publish", "HEAD is not what origin's main points at")
        self.refused("gh workflow run release-npm.yml --ref main", "HEAD is not what origin's main points at")

    def test_ship_of_another_commit_is_refused(self):
        self.make("1.2.0", "1.2.1")
        self.refused("lanefather promote d52ab67d --ship", "is not this checkout's HEAD")

    def test_no_remote_means_no_standing_pass(self):  # F1
        self.make("1.2.0", "1.2.1")
        self.git("remote", "set-url", "origin", str(self.tmp / "missing.git"))
        self.refused("bun run release:publish", "cannot read origin's main and tags")

    def test_access_change_since_the_last_release_is_refused(self):
        self.make("1.2.0", "1.2.1")
        self.write("1.2.1", publish_config={"access": "public"})
        self.git("commit", "-qam", "go public")
        self.git("push", "-q", "origin", "main")
        self.refused("bun run release:publish", "access changed since v1.2.0: the owner's call")

    def test_more_than_one_publishable_package_is_refused(self):  # F10
        self.make("1.2.0", "1.2.1")
        other = self.repo / "packages" / "other"
        other.mkdir()
        (other / "package.json").write_text(json.dumps({"name": "@acme/other", "version": "2.0.0"}))
        self.git("add", "-A")
        self.git("commit", "-qm", "second package")
        self.git("push", "-q", "origin", "main")
        self.refused("bun run release:publish", "more than one publishable package (@acme/grid, @acme/other)")

    def test_unparseable_version_is_refused(self):
        self.make("1.2.0", "1.3.0-beta.1")
        self.refused("bun run release:publish", "cannot read a plain x.y.z version")

    # ---- the shape: anything else is not eligible ----------------------------------------------------------------

    def test_commands_beside_or_around_a_release_get_no_standing_pass(self):  # F1, F2, F3, F4
        sha = self.make("1.2.0", "1.2.1")
        decoy = self.tmp / "decoy"
        for command in (
            "npm version major && npm publish",
            "sed -i '' 's/1.2.0/2.0.0/' packages/grid/package.json && npm publish",
            f"(cd {decoy}) && npm publish",
            f"if false; then cd {decoy}; fi && bun run release:publish",
            f"true || cd {decoy}; npm publish",
            "npm publish",
            f"npm publish {decoy}",
            "npm publish ./grid-1.2.1.tgz",
            f"git -C {decoy} push origin v1.2.1",
            f"GIT_DIR={decoy}/.git git push origin v1.2.1",
            f"env -C {decoy} npm publish",
            "gh release create v1.2.1 -R acme/unopted",
            "gh workflow run release.yml -R acme/unopted",
            "gh workflow run release-npm.yml --ref main -R acme/unopted",
            "git push origin v1.2.1",
            "bun run release:publish -- --access public",
            "bun run release:publish && git push origin v1.2.1",
            f"lanefather promote \"{sha}\" --ship",
            "lanefather promote HEAD --ship",
            "cd . && bun run release:publish",
        ):
            with self.subTest(command):
                self.refused(command, "standing permission covers only")

    def test_a_subdirectory_gets_no_standing_pass(self):  # F2
        sha = self.make("1.2.0", "1.2.1")
        for command in (f"lanefather promote {sha} --ship", "gh workflow run release-npm.yml --ref main",
                        "bun run release:publish"):
            self.refused(command, "run it from the repository root", cwd="{home}/grid/packages/grid")

    def test_outside_a_repository_is_refused(self):
        self.refused("bun run release:publish", "not inside a Git repository", cwd=str(self.tmp))

    # ---- the variable, the card and the refusal -------------------------------------------------------------------

    def test_variable_path_still_grants_what_the_standing_permission_does_not(self):
        self.make("1.2.0", "2.0.0")
        self.assertIsNone(self.decide("bun run release:publish", MASTACK_RELEASE_OK="@acme/grid@2.0.0"))
        self.assertIsNone(self.decide("gh workflow run release-npm.yml --ref main",
                                      MASTACK_RELEASE_OK="@acme/grid@2.0.0"))  # F9
        self.refused("bun run release:publish", "major step", MASTACK_RELEASE_OK="@acme/grid@2.1.0")

    def test_owner_only_refusal_does_not_offer_the_variable(self):  # F9
        self.make("1.2.0", "1.2.1")
        reason = self.refused("gh repo edit --visibility public", "the owner's command each time",
                              MASTACK_RELEASE_OK="@acme/grid@1.2.1")
        self.assertNotIn("set `MASTACK_RELEASE_OK=", reason)

    def test_card_only_where_it_reaches_the_owner(self):
        self.make("1.2.0", "2.0.0")
        for mode in ("default", "acceptEdits", "bypassPermissions"):
            for script in ("release_guard.py", "bash_guard.py"):
                with self.subTest(mode=mode, script=script):
                    output = self.decide("bun run release:publish", script=script, entrypoint="t3-code",
                                         permission_mode=mode)
                    decision = output["hookSpecificOutput"]
                    self.assertEqual(decision["permissionDecision"], "ask")
                    self.assertIn("`bun run release:publish`", decision["permissionDecisionReason"])
                    self.assertIn("@acme/grid 1.2.0 -> 2.0.0 is a major step", decision["permissionDecisionReason"])
        # Where `ask` is auto-approved, unproven, or asked of a subagent no one watches: deny.
        for entrypoint, payload in (("t3-code", {"permission_mode": "auto"}),
                                    ("t3-code", {"permission_mode": "dontAsk"}),
                                    ("t3-code", {"permission_mode": "plan"}),
                                    ("t3-code", {"permission_mode": "bypassPermissions", "turn_id": "t1"}),
                                    ("t3-code", {"permission_mode": "bypassPermissions", "agent_id": "a1"}),  # F11
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

    # ---- fail closed ----------------------------------------------------------------------------------------------

    def test_spent_budget_refuses_a_release_instead_of_passing_it(self):  # F5
        import bash_guard
        saved = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update(self.env)
            hook_io_reset()
            decision = bash_guard.decide({"tool_input": {"command": "npm publish"}, "cwd": str(self.project)},
                                         budget=-1.0)
            self.assertEqual(decision[0], "deny")
            self.assertIn("release-guard could not finish", decision[1])
            hook_io_reset()
            self.assertIsNone(bash_guard.decide({"tool_input": {"command": "ls"}, "cwd": str(self.project)},
                                                budget=-1.0))
        finally:
            os.environ.clear()
            os.environ.update(saved)
            hook_io_reset()


if __name__ == "__main__":
    unittest.main()
