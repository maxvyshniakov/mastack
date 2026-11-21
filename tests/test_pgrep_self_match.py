#!/usr/bin/env python3
"""Tests for hooks/pgrep_self_match.py."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from hook_test_support import HookCase, fixture  # noqa: E402


class PgrepSelfMatchTests(HookCase):
    cases = fixture("pgrep-self-match.json")

    def decide(self, command, script="pgrep_self_match.py"):
        return self.bash(script, command, "{home}")

    @staticmethod
    def expect(test, case, reason):
        for pattern in case["patterns"]:
            test.assertIn(repr(pattern), reason)
        test.assertIn("[l]ane check X", reason)
        test.assertIn("kill -0 $pid", reason)

    def test_pgrep_f_finds_a_shell_whose_command_holds_the_pattern(self):
        # The premise: a shell running a command with the plain pattern (an earlier wait loop) is found; one
        # running the bracketed form is not, since "[x]yz" does not contain "xyz".
        marker = f"self-match-{os.getpid()}"
        bracketed = f"[{marker[0]}]{marker[1:]}"

        def found(text, pattern):
            loop = subprocess.Popen(["/bin/sh", "-c", f"sleep 30; : {text}"], start_new_session=True)
            self.addCleanup(lambda: (loop.kill(), loop.wait()))
            time.sleep(0.2)
            hits = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True).stdout.split()
            loop.kill()
            loop.wait()
            return str(loop.pid) in hits

        self.assertTrue(found(marker, marker))
        self.assertFalse(found(bracketed, bracketed))

    def test_patterns_that_match_their_own_command_are_denied_with_the_fix(self):
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.expect(self, case, self.denied(self.decide(case["command"])))

    def test_bracketed_variable_and_name_only_forms_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"]))

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("pgrep_self_match.py")
        self.assertIsNone(self.decide("pgrep -f \"unterminated"))


if __name__ == "__main__":
    unittest.main()
