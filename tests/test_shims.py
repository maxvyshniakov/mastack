#!/usr/bin/env python3
"""Tests for cross-harness PATH shims (bin/install-shims + bin/shim-exec)."""
from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class ShimTests(unittest.TestCase):
    def test_shims_deny_blocked_git_commands_and_pass_safe_ones(self):
        with tempfile.TemporaryDirectory(prefix="mastack-shims-") as tmp:
            base = pathlib.Path(tmp)
            shim_dir = base / "shims"
            config_dir = base / "config"
            state_dir = base / "state"
            config_dir.mkdir()
            (config_dir / "hooks.json").write_text("{}\n")

            subprocess.run(["bash", str(ROOT / "bin/install-shims"), "--dir", str(shim_dir)],
                           check=True, capture_output=True, text=True)
            self.assertTrue((shim_dir / "git").is_file())

            env = {**os.environ, "PATH": f"{shim_dir}:{os.environ.get('PATH', '')}",
                   "MASTACK_CONFIG": str(config_dir), "MASTACK_HOOK_STATE": str(state_dir)}

            denied = subprocess.run(["git", "stash"], env=env, capture_output=True, text=True)
            self.assertEqual(denied.returncode, 126)
            self.assertIn("mastack shim (deny)", denied.stderr)
            self.assertIn("[stash]", denied.stderr)

            ok = subprocess.run(["git", "--version"], env=env, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("git version", ok.stdout)

            subprocess.run(["bash", str(ROOT / "bin/install-shims"), "--dir", str(shim_dir), "--uninstall"],
                           check=True, capture_output=True, text=True)
            self.assertFalse((shim_dir / "git").exists())


if __name__ == "__main__":
    unittest.main()
