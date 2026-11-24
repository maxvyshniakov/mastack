#!/usr/bin/env python3
"""Tests for bin/lane-receipt and bin/quiet-cap."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class LaneReceiptTests(unittest.TestCase):
    def test_emits_branch_sha_outside_claims_and_new_tests(self):
        with tempfile.TemporaryDirectory(prefix="mastack-receipt-") as tmp:
            repo = pathlib.Path(tmp)
            env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
            env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")

            def git(*args):
                return subprocess.check_output(["git", "-C", str(repo), *args], env=env, text=True).strip()

            git("init", "-q", "-b", "lane/demo")
            (repo / "src").mkdir()
            (repo / "src/a.py").write_text("x = 1\n")
            git("add", ".")
            git("-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", "base")
            base = git("rev-parse", "HEAD")

            (repo / "tests").mkdir()
            (repo / "src/a.py").write_text("x = 2\n")
            (repo / "tests/test_a.py").write_text("assert True\n")
            (repo / "README.md").write_text("hi\n")
            git("add", ".")
            git("-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", "change")

            proc = subprocess.run(
                [sys.executable, str(ROOT / "bin/lane-receipt"), "--base", base, "--claims", "src/**", "tests/**", "--json"],
                cwd=repo, env=env, capture_output=True, text=True, check=True,
            )
            data = json.loads(proc.stdout)
            self.assertEqual(data["branch"], "lane/demo")
            self.assertEqual(data["outside_claims"], ["README.md"])
            self.assertEqual(data["new_tests"], ["tests/test_a.py"])


class QuietCapTests(unittest.TestCase):
    def test_short_output_passes_verbatim_and_large_output_is_capped_with_log_path(self):
        short = subprocess.run([sys.executable, str(ROOT / "bin/quiet-cap"), "--", sys.executable, "-c", "print('ok')"],
                               capture_output=True, text=True)
        self.assertEqual(short.returncode, 0)
        self.assertEqual(short.stdout, "ok\n")

        script = "for i in range(200):\n print(f'line {i}' if i != 100 else 'FAIL: boom')\nimport sys; sys.exit(3)"
        capped = subprocess.run([sys.executable, str(ROOT / "bin/quiet-cap"), "--max-chars", "500", "--",
                                 sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(capped.returncode, 3)
        self.assertIn("lines omitted; full output:", capped.stdout)
        self.assertIn("FAIL: boom", capped.stdout)
        self.assertLess(len(capped.stdout), 3000)


if __name__ == "__main__":
    unittest.main()
