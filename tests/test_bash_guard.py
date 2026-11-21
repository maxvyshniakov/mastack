#!/usr/bin/env python3
"""Tests for hooks/bash_guard.py dispatcher."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_codex_credits  # noqa: E402
import test_docker_desktop  # noqa: E402
import test_git_guard  # noqa: E402
import test_pgrep_self_match  # noqa: E402
import test_release_guard  # noqa: E402
import test_shell_pitfalls  # noqa: E402
import test_simctl_boot  # noqa: E402
import test_slot_label  # noqa: E402
import test_unguarded_sequence  # noqa: E402
import test_zsh_word_split  # noqa: E402
from hook_test_support import HOOKS, HookCase, hook_io_reset  # noqa: E402


class BashGuardTests(HookCase):
    """bash_guard.py runs every check in one process and decides as they do."""

    def test_every_fixture_decides_as_its_check_does(self):
        """A deny case is denied with the check's own reason; an allow case gets no block from that check (another
        check may deny it: a pipe-masked merge in an unguarded-sequence fixture is git-guard's)."""
        sets = [(test_git_guard.GitGuardTests, test_git_guard.GitGuard.cases, test_git_guard.GitGuard.expect,
                 ("git-guard denied",), lambda t, c: t.decide(c, "bash_guard.py")),
                (test_zsh_word_split.ZshWordSplitTests, test_zsh_word_split.ZshWordSplitTests.cases,
                 test_zsh_word_split.ZshWordSplitTests.expect, ("zsh word-split denied",),
                 lambda t, c: t.decide(c["command"], "bash_guard.py")),
                (test_unguarded_sequence.UnguardedSequenceTests, test_unguarded_sequence.UnguardedSequenceTests.cases,
                 test_unguarded_sequence.UnguardedSequenceTests.expect, ("unguarded-sequence denied",),
                 lambda t, c: t.decide(c["command"], script="bash_guard.py")),
                (test_pgrep_self_match.PgrepSelfMatchTests, test_pgrep_self_match.PgrepSelfMatchTests.cases,
                 test_pgrep_self_match.PgrepSelfMatchTests.expect, ("pgrep-self-match denied",),
                 lambda t, c: t.decide(c["command"], "bash_guard.py")),
                (test_shell_pitfalls.ShellPitfallsTests, test_shell_pitfalls.ShellPitfallsTests.cases,
                 test_shell_pitfalls.ShellPitfallsTests.expect, ("macOS has no", "BSD cat"),
                 lambda t, c: t.decide(c["command"], "bash_guard.py")),
                (test_slot_label.SlotLabelTests, test_slot_label.SlotLabelTests.cases,
                 test_slot_label.SlotLabelTests.expect, ("slot-label denied",),
                 lambda t, c: t.decide(c, "bash_guard.py")),
                (test_codex_credits.CodexCreditsTests, test_codex_credits.CodexCreditsTests.cases,
                 test_codex_credits.CodexCreditsTests.expect, ("codex-credits denied",),
                 lambda t, c: t.decide(c, "bash_guard.py")),
                (test_docker_desktop.DockerDesktopTests, test_docker_desktop.DockerDesktopTests.cases,
                 test_docker_desktop.DockerDesktopTests.expect, ("docker-desktop denied",),
                 lambda t, c: t.decide(c["command"], "bash_guard.py")),
                (test_simctl_boot.SimctlBootTests, test_simctl_boot.SimctlBootTests.cases,
                 test_simctl_boot.SimctlBootTests.expect, ("simctl-boot denied",),
                 lambda t, c: t.decide(c["command"], "bash_guard.py")),
                (test_release_guard.ReleaseGuardTests, test_release_guard.ReleaseGuardTests.cases,
                 test_release_guard.ReleaseGuardTests.expect, ("release-guard denied",),
                 lambda t, c: t.decide(c["command"], "bash_guard.py"))]
        for kind, cases, expect, mine, decide in sets:
            runner = kind()
            runner.__dict__.update(self.__dict__)
            if hasattr(kind, "setUp") and kind.setUp is not HookCase.setUp:
                (self.project / "package.json").write_text(json.dumps({"name": "@acme/ui-kit", "version": "1.2.0"}))
            for case in cases["deny"]:
                with self.subTest(f"{kind.__name__}: {case['name']}"):
                    expect(self, case, self.denied(decide(runner, case)))
            for case in cases["allow"]:
                with self.subTest(f"{kind.__name__}: {case['name']}"):
                    output = decide(runner, case)
                    blocks = output["hookSpecificOutput"]["permissionDecisionReason"].split("\n\n") if output else []
                    self.assertFalse([b for b in blocks if b.startswith(mine)], blocks)

    def test_a_command_two_checks_deny_names_both(self):
        reason = self.denied(self.bash("bash_guard.py", "cd x; git push origin main", "{home}/app"))
        self.assertIn("[push-by-name]", reason)
        self.assertIn("unguarded-sequence denied", reason)

    def test_a_plain_command_loads_no_parser(self):
        probe = ("import json, sys; sys.path.insert(0, sys.argv[1]); import bash_guard; "
                 "bash_guard.decide({'tool_input': {'command': sys.argv[2]}}); "
                 "print(json.dumps(sorted(m for m in sys.modules if m == 'shell' or m.endswith(('_guard', "
                 "'_sequence', '_split', '_match', '_pitfalls')))))")
        loaded = lambda command: json.loads(subprocess.run([sys.executable, "-c", probe, str(HOOKS), command],
                                                           capture_output=True, text=True, env=self.env).stdout)
        self.assertEqual(loaded("ls -la"), ["bash_guard", "shell_pitfalls"])
        self.assertEqual(loaded("cd x && git status"), ["bash_guard", "git_guard", "shell_pitfalls"])

    def test_a_failing_check_is_logged_and_the_others_still_decide(self):
        import bash_guard
        import git_guard
        with mock.patch.dict(os.environ, {"MASTACK_HOOK_STATE": str(self.tmp / "state")}), \
                mock.patch.object(git_guard, "check", side_effect=RuntimeError("boom")):
            hook_io_reset()
            decision = bash_guard.decide({"tool_input": {"command": "cd x; git commit -qm wip"}, "cwd": str(self.tmp)})
        hook_io_reset()
        self.assertEqual(decision[0], "deny")
        self.assertIn("unguarded-sequence denied", decision[1])
        self.assertIn("git-guard error RuntimeError('boom')", (self.tmp / "state" / "guard.log").read_text())

    def test_the_lease_guard_is_skipped_once_a_check_denied(self):
        import bash_guard
        import lease_guard
        with mock.patch.object(lease_guard, "check") as lease:
            decision = bash_guard.decide({"tool_input": {"command": "git stash; kill 12345"}, "cwd": str(self.tmp)})
        hook_io_reset()
        self.assertIn("[stash]", decision[1])
        lease.assert_not_called()

    def test_a_spent_budget_answers_with_what_was_found(self):
        import bash_guard
        import lease_guard
        import unguarded_sequence
        import zsh_word_split
        slow = lambda data: time.sleep(0.3)
        with mock.patch.dict(os.environ, {"MASTACK_HOOK_STATE": str(self.tmp / "state")}), \
                mock.patch.object(zsh_word_split, "check", side_effect=slow), \
                mock.patch.object(unguarded_sequence, "check") as later, mock.patch.object(lease_guard, "check"):
            hook_io_reset()
            decision = bash_guard.decide({"tool_input": {"command": "git stash; echo $x"}}, budget=0.2)
        hook_io_reset()
        self.assertEqual(decision[0], "deny")
        self.assertIn("[stash]", decision[1])
        later.assert_not_called()
        self.assertIn("budget spent before unguarded-sequence", (self.tmp / "state" / "guard.log").read_text())

    def test_subprocesses_get_only_what_is_left_of_the_budget(self):
        import hook_io
        import lease_guard
        hook_io.set_budget(1.0)
        self.assertLessEqual(hook_io.timeout(5), 1.0)
        hook_io.set_budget(0)
        with self.assertRaises(hook_io.OutOfTime):
            hook_io.timeout(5)
        with self.assertRaises(lease_guard.Unresolved):
            lease_guard.run(["pgrep", "-f", "x"])
        self.assertIsNone(lease_guard.status("slotfather"))
        hook_io_reset()

    def test_the_budget_fits_the_registered_timeout(self):
        import bash_guard
        import lifecycle
        import register
        self.assertEqual(register.handler()["timeout"], bash_guard.HOOK_TIMEOUT)
        self.assertLess(bash_guard.BUDGET + 1.5, bash_guard.HOOK_TIMEOUT)
        self.assertEqual(register.lifecycle_handler("Stop")["timeout"], lifecycle.HOOK_TIMEOUT)
        self.assertLess(lifecycle.BUDGET + 1.5, lifecycle.HOOK_TIMEOUT)

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("bash_guard.py")


if __name__ == "__main__":
    unittest.main()
