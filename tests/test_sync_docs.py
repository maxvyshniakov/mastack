#!/usr/bin/env python3
"""Tests for bin/sync-docs --check and bin/eval CLI flags."""
from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class SyncDocsTests(unittest.TestCase):
    def test_sync_docs_check_passes_on_repository(self):
        proc = subprocess.run([sys.executable, str(ROOT / "bin/sync-docs"), "--check"],
                              cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("sync-docs: ok", proc.stdout)

    def test_eval_help_exposes_without_skill_and_antigravity(self):
        proc = subprocess.run([sys.executable, str(ROOT / "bin/eval"), "--help"],
                              cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertIn("--without-skill", proc.stdout)
        self.assertIn("antigravity", proc.stdout)


if __name__ == "__main__":
    unittest.main()
