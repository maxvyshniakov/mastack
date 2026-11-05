#!/usr/bin/env python3
"""The pre-push test runner isolates fixture Git commands from the pushed repository."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class CheckTests(unittest.TestCase):
    def test_hook_git_context_cannot_change_the_pushed_repository(self):
        for with_index in (False, True):
            with self.subTest(with_index=with_index):
                self.check_hook_context(with_index)

    def check_hook_context(self, with_index):
        with tempfile.TemporaryDirectory(prefix="mastack-check-") as temporary:
            root = Path(temporary)
            (root / "bin").mkdir()
            (root / "tests").mkdir()
            shutil.copyfile(ROOT / "bin/check", root / "bin/check")
            patterns = root / "patterns"
            patterns.write_text("")
            (root / "tests/probe_test.py").write_text('''
from pathlib import Path
import subprocess
import tempfile
with tempfile.TemporaryDirectory() as temporary:
    child = Path(temporary) / "child"
    subprocess.run(["git", "init", "-q", str(child)], check=True)
    subprocess.run(["git", "-C", str(child), "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@example.com", "commit", "-q",
                    "--allow-empty", "-m", "fixture"], check=True)
    subprocess.run(["git", "init", "-q", "--bare", str(Path(temporary) / "bare")], check=True)
''')
            env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
            env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")

            def git(*args):
                return subprocess.check_output(["git", "-C", str(root), *args], env=env, text=True).strip()

            git("init", "-q", "-b", "fixture")
            git("add", ".")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.com", "commit", "-qm", "base")
            original = git("rev-parse", "HEAD")
            context = {**env, "GIT_DIR": str(root / ".git")}
            if with_index:
                context["GIT_INDEX_FILE"] = str(root / ".git/index")
            result = subprocess.run([sys.executable, str(root / "bin/check"), "--patterns", str(patterns)],
                                    cwd=root, env=context, capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            bare = subprocess.check_output(["git", "--git-dir", str(root / ".git"), "config", "--get", "core.bare"],
                                           env=env, text=True).strip()
            head = subprocess.check_output(["git", "--git-dir", str(root / ".git"), "rev-parse", "HEAD"],
                                           env=env, text=True).strip()
            self.assertEqual(("false", original), (bare, head), "fixture Git mutated the pushed repository")


if __name__ == "__main__":
    unittest.main()
