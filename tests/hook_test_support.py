"""Shared harness for the hook tests under tests/test_*.py."""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"
FIXTURES = HOOKS / "fixtures"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

# The project steps the unguarded-sequence fixtures were recorded with, as a project's docs/agents/hooks.json.
PROJECT_STEPS = ["tools/lane land", "tools/lane promote", "tools/lane start", "tools/lane adopt", "tools/lane done",
                 "tools/lane review --mark", "tools/lane review --fix-lane", "app-link/deploy.sh",
                 "app-link/build-package.sh", "install-control-app.sh"]


def hook_io_reset():
    """Forget what an in-process call cached: the machine settings and the time budget."""
    import hook_io
    hook_io._config = None
    hook_io._deadline = None


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class HookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="mastack-hooks-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.config = self.tmp / "config"
        for directory in (self.home, self.config):
            directory.mkdir()
        self.settings({"checkouts": ["~/app", "~/kit", "~/grid"]})
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("MASTACK_") and k != "XDG_STATE_HOME"}
        self.env.update(HOME=str(self.home), MASTACK_CONFIG=str(self.config), MASTACK_HOOK_STATE=str(self.tmp / "state"))
        # A project with its own steps, as the unguarded-sequence fixtures expect.
        self.project = self.home / "app"
        (self.project / ".git").mkdir(parents=True)
        (self.project / "docs" / "agents").mkdir(parents=True)
        (self.project / "docs" / "agents" / "hooks.json").write_text(json.dumps({"mutating_steps": PROJECT_STEPS}))

    def settings(self, values: dict):
        (self.config / "hooks.json").write_text(json.dumps(values))

    def fill(self, text: str) -> str:
        return text.replace("{home}", str(self.home))

    def run_hook(self, script: str, payload: dict | str) -> dict | None:
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        proc = subprocess.run([sys.executable, str(HOOKS / script)], input=stdin, capture_output=True, text=True,
                              env=self.env, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout) if proc.stdout.strip() else None

    def bash(self, script: str, command: str, cwd: str | None = None, **extra) -> dict | None:
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": self.fill(command)},
                   **({"cwd": self.fill(cwd)} if cwd else {}), **extra}
        return self.run_hook(script, payload)

    def denied(self, output) -> str:
        self.assertIsNotNone(output, "allowed")
        decision = output["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        return decision["permissionDecisionReason"]

    def assertFailsOpen(self, script: str):
        self.assertIsNone(self.run_hook(script, {"tool_name": "Bash", "tool_input": {}}))
        self.assertIsNone(self.run_hook(script, "not json"))
