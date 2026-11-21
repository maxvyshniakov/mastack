#!/usr/bin/env python3
"""Tests for hooks/unguarded_sequence.py."""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from hook_test_support import HookCase, PROJECT_STEPS, fixture  # noqa: E402


class UnguardedSequenceTests(HookCase):
    cases = fixture("unguarded-sequence.json")

    def decide(self, command, cwd=None, script="unguarded_sequence.py"):
        return self.bash(script, command, cwd or str(self.project))

    @staticmethod
    def expect(test, case, reason):
        block = next(part for part in reason.split("\n\n") if part.startswith("unguarded-sequence denied"))
        rule, *findings = block.splitlines()
        test.assertIn("`&&`", rule)
        test.assertIn("|| exit 1" if case.get("errexit") else "set -e", rule)
        for step in case["steps"]:
            shown = f"`{test.fill(step)}"[:60]  # a long path is shortened in the message
            test.assertTrue(any(shown in line for line in findings), f"{step!r} not named in {reason}")

    def test_shells_run_the_next_step_after_a_failure(self):
        # The premise: `;` goes on after a failure, and set -e does not stop on a failure before `&&`, one a `||`
        # handler swallows, or one inside a pipeline without pipefail; with pipefail it does.
        if not shutil.which("zsh"):
            self.skipTest("no zsh")
        script = ("false; print -n a; set -e; false && true; print -n b; false || print -n c; false | true; "
                  "print -n d; true || exit 1; print e; setopt pipe_fail; false | true; print f")
        self.assertEqual(subprocess.run(["zsh", "-f", "-c", script], capture_output=True, text=True).stdout, "abcde\n")

    def test_mutating_steps_after_an_unguarded_step_are_denied_with_the_fix(self):
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.expect(self, case, self.denied(self.decide(case["command"])))

    def test_guarded_or_read_only_look_alikes_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"]))

    def test_canonical_dispatcher_guards_lanefather_global_config_promotion(self):
        command = "cd /missing; lanefather --config /tmp/project.toml promote abc --install"
        self.assertIn("lanefather --config", self.denied(self.decide(command, script="bash_guard.py")))

    def test_project_lane_wrappers_share_lanefather_semantics_only_where_declared(self):
        facts = self.project / "docs/agents/hooks.json"
        facts.write_text(json.dumps({"mutating_steps": PROJECT_STEPS, "lanefather_commands": ["tools/lane"]}))
        forms = ["tools/lane", "/work/tools/lane", "env MODE=x tools/lane",
                 "/usr/bin/env -u MODE /work/tools/lane", "python3 -B /work/tools/lane"]
        for script in ("unguarded_sequence.py", "bash_guard.py"):
            for form in forms:
                for config in ("--config /tmp/project.toml", "--config=/tmp/project.toml"):
                    with self.subTest(script=script, form=form, config=config):
                        command = f"cd /missing; {form} {config} promote abc --install"
                        self.assertIn("promote", self.denied(self.decide(command, script=script)))
                for suffix in ("--config x show lane --json", "--config=x list", "review lane", "gc --dry-run"):
                    with self.subTest(script=script, form=form, suffix=suffix):
                        self.assertIsNone(self.decide(f"cd /missing; {form} {suffix}", script=script))
        elsewhere = self.tmp / "unconfigured"
        (elsewhere / ".git").mkdir(parents=True)
        self.assertIsNone(self.decide("cd /missing; tools/lane --config x promote abc", str(elsewhere)))

    def test_project_steps_come_from_the_sessions_repository(self):
        elsewhere = self.tmp / "elsewhere"
        (elsewhere / ".git").mkdir(parents=True)
        command = "cd ..; tools/lane land 5-x"
        self.assertIn("`tools/lane land", self.denied(self.decide(command)))
        self.assertIn("`tools/lane land", self.denied(self.decide(command, str(self.project / "desktop" / "src"))))
        self.assertIsNone(self.decide(command, str(elsewhere)))
        self.assertIsNone(self.decide(command, str(self.tmp)))
        self.assertIn("`git merge", self.denied(self.decide("cd ..; git merge x", str(elsewhere))), "git is everywhere")

    def test_a_worktree_without_the_file_reads_its_main_checkout(self):
        main, worktree = self.tmp / "main", self.tmp / "lane"
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run([*git, "init", "-q", str(main)], check=True)
        subprocess.run([*git, "-C", str(main), "commit", "-q", "--allow-empty", "-m", "base"], check=True)
        subprocess.run([*git, "-C", str(main), "worktree", "add", "-q", str(worktree)], check=True, capture_output=True)
        command = "cd ..; ./deploy.sh"
        self.assertIsNone(self.decide(command, str(worktree)))
        (main / "docs" / "agents").mkdir(parents=True)
        (main / "docs" / "agents" / "hooks.json").write_text(json.dumps({"mutating_steps": ["deploy.sh"]}))
        self.assertIn("`./deploy.sh", self.denied(self.decide(command, str(worktree))))
        (worktree / "docs" / "agents").mkdir(parents=True)
        (worktree / "docs" / "agents" / "hooks.json").write_text(json.dumps({"mutating_steps": []}))
        self.assertIsNone(self.decide(command, str(worktree)), "the worktree's own file wins")

    def test_machine_steps_apply_to_every_project(self):
        self.settings({"mutating_steps": ["bin/release"]})
        self.assertIn("`bin/release", self.denied(self.decide("make; bin/release 1.0", str(self.tmp))))

    def test_machine_and_project_steps_add_up(self):
        self.settings({"mutating_steps": ["bin/release"]})
        reason = self.denied(self.decide("make; bin/release 1.0; tools/lane land 5-x"))
        self.assertIn("`bin/release", reason)
        self.assertIn("`tools/lane land", reason)

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("unguarded_sequence.py")
        self.assertIsNone(self.decide("cd $W; git merge \"unterminated"))
        (self.project / "docs" / "agents" / "hooks.json").write_text("{not json")
        self.assertIsNone(self.decide("cd ..; tools/lane land 5-x"), "an unreadable project file adds no steps")


if __name__ == "__main__":
    unittest.main()
