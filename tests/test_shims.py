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
    def test_shims_deny_blocked_commands_handle_relative_dir_nested_shims_and_release_ok(self):
        with tempfile.TemporaryDirectory(prefix="mastack-shims-") as tmp:
            base = pathlib.Path(tmp)
            shim_dir2 = base / "shims2"
            config_dir = base / "config"
            state_dir = base / "state"
            config_dir.mkdir()
            (config_dir / "hooks.json").write_text("{}\n")

            # Install using a relative --dir path to verify no exec loop from another cwd.
            subprocess.run(["bash", str(ROOT / "bin/install-shims"), "--dir", "relshims"],
                           cwd=base, check=True, capture_output=True, text=True)
            shim_dir = base / "relshims"
            subprocess.run(["bash", str(ROOT / "bin/install-shims"), "--dir", str(shim_dir2)],
                           check=True, capture_output=True, text=True)

            env = {**os.environ, "PATH": f"{shim_dir}:{shim_dir2}:{os.environ.get('PATH', '')}",
                   "MASTACK_CONFIG": str(config_dir), "MASTACK_HOOK_STATE": str(state_dir)}

            denied = subprocess.run(["git", "stash"], cwd="/tmp", env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(denied.returncode, 126)
            self.assertIn("[stash]", denied.stderr)

            # MASTACK_RELEASE_OK in env cannot self-grant release permission through a shim.
            rel = subprocess.run(["gh", "release", "create", "v1.2.3"], cwd="/tmp",
                                 env={**env, "MASTACK_RELEASE_OK": "v1.2.3"},
                                 capture_output=True, text=True, timeout=15)
            self.assertEqual(rel.returncode, 126)

            ok = subprocess.run(["git", "--version"], cwd="/tmp", env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("git version", ok.stdout)

            # Uninstall only removes mastack shims, never foreign files.
            foreign = base / "foreign"
            foreign.mkdir()
            (foreign / "git").write_text("#!/bin/sh\necho foreign\n")
            subprocess.run(["bash", str(ROOT / "bin/install-shims"), "--dir", str(foreign), "--uninstall"],
                           check=True, capture_output=True, text=True)
            self.assertTrue((foreign / "git").exists())

            subprocess.run(["bash", str(ROOT / "bin/install-shims"), "--dir", str(shim_dir), "--uninstall"],
                           check=True, capture_output=True, text=True)
            self.assertFalse((shim_dir / "git").exists())


if __name__ == "__main__":
    unittest.main()
