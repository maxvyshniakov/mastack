#!/usr/bin/env python3
"""Tests for bin/sync-docs --check and bin/eval CLI flags."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_sync_docs():
    loader = importlib.machinery.SourceFileLoader("sync_docs", str(ROOT / "bin/sync-docs"))
    spec = importlib.util.spec_from_loader("sync_docs", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class SyncDocsTests(unittest.TestCase):
    def test_sync_docs_check_passes_on_repository(self):
        proc = subprocess.run([sys.executable, str(ROOT / "bin/sync-docs"), "--check"],
                              cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("sync-docs: ok", proc.stdout)

    def test_sync_docs_catches_first_choice_effort_drift(self):
        mod = load_sync_docs()
        with tempfile.TemporaryDirectory(prefix="mastack-sync-") as tmp:
            root = pathlib.Path(tmp)
            (root / "models.toml").write_text(
                '[roles.implement]\nchoices = [{ model = "opus", effort = "high" }]\n'
            )
            (root / "models.md").write_text(
                "| implement | Opus, medium | Sol, xhigh | why |\n"
            )
            problems = mod.check_models_md(root)
            self.assertTrue(any("first choice mismatch" in p for p in problems), problems)

    def test_eval_help_exposes_without_skill(self):
        proc = subprocess.run([sys.executable, str(ROOT / "bin/eval"), "--help"],
                              cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertIn("--without-skill", proc.stdout)


if __name__ == "__main__":
    unittest.main()
