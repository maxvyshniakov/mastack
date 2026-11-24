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
    def test_multi_commit_default_base_dir_claims_and_invalid_base(self):
        with tempfile.TemporaryDirectory(prefix="mastack-receipt-") as tmp:
            repo = pathlib.Path(tmp)
            env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
            env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")

            def git(*args):
                return subprocess.check_output(["git", "-C", str(repo), *args], env=env, text=True).strip()

            git("init", "-q", "-b", "main")
            (repo / "src").mkdir()
            (repo / "src/a.py").write_text("x = 1\n")
            git("add", ".")
            git("-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", "base")

            git("checkout", "-qb", "lane/demo")
            (repo / "OUTSIDE.md").write_text("oops\n")
            git("add", ".")
            git("-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", "first")

            (repo / "tests").mkdir()
            (repo / "src/a.py").write_text("x = 2\n")
            (repo / "tests/test_a.py").write_text("assert True\n")
            git("add", ".")
            git("-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", "second")

            proc = subprocess.run(
                [sys.executable, str(ROOT / "bin/lane-receipt"), "--claims", "src/", "tests/**", "--json"],
                cwd=repo, env=env, capture_output=True, text=True, check=True,
            )
            data = json.loads(proc.stdout)
            self.assertEqual(data["branch"], "lane/demo")
            self.assertEqual(data["outside_claims"], ["OUTSIDE.md"])
            self.assertEqual(data["new_tests"], ["tests/test_a.py"])

            bad = subprocess.run([sys.executable, str(ROOT / "bin/lane-receipt"), "--base", "nosuchref"],
                                 cwd=repo, env=env, capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)


class QuietCapTests(unittest.TestCase):
    def test_enforces_max_chars_on_long_lines_non_utf8_and_missing_command(self):
        short = subprocess.run([sys.executable, str(ROOT / "bin/quiet-cap"), "--", sys.executable, "-c", "print('ok')"],
                               capture_output=True, text=True)
        self.assertEqual(short.returncode, 0)
        self.assertEqual(short.stdout, "ok\n")

        long_lines = "for i in range(200): print('x' * 5000 if i != 100 else 'ValueError: boom')\nimport sys; sys.exit(3)"
        capped = subprocess.run([sys.executable, str(ROOT / "bin/quiet-cap"), "--max-chars", "1000", "--",
                                 sys.executable, "-c", long_lines], capture_output=True, text=True)
        self.assertEqual(capped.returncode, 3)
        self.assertIn("capped at 1000 chars", capped.stdout)
        self.assertIn("ValueError: boom", capped.stdout)
        self.assertLessEqual(len(capped.stdout), 1200)

        non_utf8 = subprocess.run([sys.executable, str(ROOT / "bin/quiet-cap"), "--",
                                   sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\xfeok\\n')"],
                                  capture_output=True, text=True)
        self.assertEqual(non_utf8.returncode, 0)

        missing = subprocess.run([sys.executable, str(ROOT / "bin/quiet-cap"), "--", "no-such-binary-mastack-test"],
                                 capture_output=True, text=True)
        self.assertEqual(missing.returncode, 127)
        self.assertNotIn("Traceback", missing.stderr)


if __name__ == "__main__":
    unittest.main()
