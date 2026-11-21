#!/usr/bin/env python3
"""Tests for hooks/zsh_word_split.py."""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from hook_test_support import HookCase, fixture  # noqa: E402


class ZshWordSplitTests(HookCase):
    cases = fixture("zsh-word-split.json")

    def decide(self, command, script="zsh_word_split.py"):
        return self.bash(script, command, "{home}")

    @staticmethod
    def expect(test, case, reason):
        test.assertIn(f"[{case['rule']}]", reason)
        test.assertIn(f"${{={case['var']}}}", reason)
        test.assertIn("array", reason)
        test.assertIn(f'"${case["var"]}"', reason, "names the quoted form for one word")

    def test_zsh_leaves_an_unquoted_scalar_whole(self):
        # The premise: zsh splits ${=var} and arrays, never a plain $var; bash splits all three.
        if not shutil.which("zsh"):
            self.skipTest("no zsh")
        script = 'v="a b"; set -- $v; print -n $#; set -- ${=v}; print -n $#; a=(a b); set -- $a; print $#'
        self.assertEqual(subprocess.run(["zsh", "-f", "-c", script], capture_output=True, text=True).stdout, "122\n")

    def test_shapes_that_do_not_split_are_denied_with_the_fix(self):
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.expect(self, case, self.denied(self.decide(case["command"])))

    def test_look_alikes_that_split_or_mean_one_word_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"]))

    def test_one_line_per_finding(self):
        reason = self.denied(self.decide("for p in \"a b\"; do set -- $p; done; for f in $files; do :; done"))
        self.assertEqual([line.split("]")[0] for line in reason.splitlines() if line.startswith("- [")],
                         ["- [set-scalar", "- [for-scalar"])

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("zsh_word_split.py")


if __name__ == "__main__":
    unittest.main()
