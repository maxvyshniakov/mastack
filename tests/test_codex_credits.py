#!/usr/bin/env python3
"""Tests for hooks/codex_credits.py."""
from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tomllib
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fake_codex  # noqa: E402
from hook_test_support import HookCase, ROOT, fixture  # noqa: E402

LEGACY_CODEX_TABLE = '''schema = 1
active_families = ["anthropic", "openai"]

[models.opus]
id = "claude-opus-test"
family = "anthropic"
cli = "claude"

[models.sol]
id = "gpt-test"
family = "openai"
cli = "codex"

[cli.claude]
option = "effort"
run = ["claude", "-p", "--model", "{id}", "--effort", "{effort}"]
review = ["claude", "-p", "--model", "{id}", "--effort", "{effort}"]

[cli.codex]
option = "model_reasoning_effort"
run = ["codex", "exec", "-c", "model=\\"{id}\\""]
review = ["codex", "review", "-c", "model=\\"{id}\\""]

[roles.review]
choices = [
  { model = "sol", effort = "medium", when = { not_family = true, limit = { codex_weekly = 15 } } },
  { model = "opus", effort = "medium" },
]
'''


class CodexCreditsTests(HookCase):
    """On the retired-Codex models.toml, headless Codex runs are denied immediately with zero subprocess latency.
    On custom tables where OpenAI/Codex is active, the weekly limit threshold still governs."""

    cases = fixture("codex-credits.json")
    models = tomllib.loads((ROOT / "models.toml").read_text())

    def stand_in(self, used: float | None = 100, shim: bool = False, **env: str):
        """codex on PATH reporting `used` percent of the weekly limit; None: no codex at all."""
        self.codex_log = self.tmp / "codex.log"
        fake_codex.install(self.tmp / "codex-bin", shim=shim)
        keep = {k: self.env[k] for k in ("HOME", "MASTACK_CONFIG", "MASTACK_HOOK_STATE")}
        self.env = fake_codex.environment(self.env, self.tmp / "codex-bin" if used is not None else None,
                                          self.codex_log, FAKE_CODEX_USED=str(used or 0), **keep, **env)

    def write_table(self, text: str) -> str:
        path = self.tmp / "models.toml"
        path.write_text(text)
        return str(path)

    def decide(self, case, script="codex_credits.py"):
        if not getattr(self, "codex_log", None):
            self.stand_in()
        return self.bash(script, case["command"], case.get("cwd", "{home}/app"))

    def reads(self) -> int:
        return fake_codex.reads(self.codex_log) if getattr(self, "codex_log", None) else 0

    @classmethod
    def expect(cls, test, case, reason):
        carbon = cls.models["models"]["carbon"]["id"]
        test.assertIn("codex-credits denied", reason)
        test.assertIn("retired", reason)
        test.assertIn(f"`{ROOT / 'bin' / 'role'} review` picks carbon ({carbon}), effort medium", reason)
        test.assertIn(f"`{ROOT / 'bin' / 'role'} <role>`", reason)
        test.assertIn("MASTACK_ALLOW_CREDITS=1", reason)

    def test_retired_codex_denies_immediately_with_zero_subprocesses(self):
        self.stand_in(used=0)
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.expect(self, case, self.denied(self.decide(case)))
        self.assertEqual(self.reads(), 0)

    def test_retired_codex_denies_even_when_codex_is_not_on_path(self):
        self.stand_in(used=None)
        reason = self.denied(self.decide({"command": "codex exec 'review'"}))
        self.expect(self, {"command": "codex exec 'review'"}, reason)
        self.assertEqual(self.reads(), 0)

    def test_mentions_help_and_the_owners_override_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case))
        self.assertEqual(self.reads(), 0)

    def test_the_override_is_logged_without_the_prompt(self):
        self.stand_in(used=100)
        self.assertIsNone(self.decide({"command": "MASTACK_ALLOW_CREDITS=1 codex exec 'secret prompt text'"}))
        logged = (self.tmp / "state" / "guard.log").read_text()
        self.assertIn("codex-credits override: codex exec", logged)
        self.assertNotIn("secret prompt text", logged)
        self.assertEqual(self.reads(), 0)

    def test_legacy_table_with_active_codex_enforces_weekly_limit(self):
        table = self.write_table(LEGACY_CODEX_TABLE)
        self.stand_in(used=100, MASTACK_MODELS=table)
        reason = self.denied(self.decide({"command": "codex exec 'review'"}))
        self.assertIn("codex-credits denied", reason)
        self.assertIn("0% left", reason)
        self.assertIn("needs 15%", reason)
        self.assertIn("claude -p --model claude-opus-test --effort medium", reason)
        self.assertEqual(self.reads(), 1)

        # Cached read is reused without spawning again.
        self.denied(self.decide({"command": "codex exec 'two'"}))
        self.assertEqual(self.reads(), 1)

        # Expired cache with room left passes.
        self.stand_in(used=50, MASTACK_MODELS=table)
        cache = self.tmp / "state" / "codex-limit.json"
        stored = json.loads(cache.read_text())
        cache.write_text(json.dumps({**stored, "read_at": stored["read_at"] - 600}))
        self.assertIsNone(self.decide({"command": "codex exec 'three'"}))
        self.assertEqual(self.reads(), 2)

    def test_legacy_table_reached_limit_and_failing_codex(self):
        table = self.write_table(LEGACY_CODEX_TABLE)
        self.stand_in(used=40, FAKE_CODEX_REACHED="rate_limit_reached", MASTACK_MODELS=table)
        self.assertIn("Codex reports rate_limit_reached", self.denied(self.decide({"command": "codex exec x"})))

        for name, env in (("missing", {"used": None}), ("silent", {"FAKE_CODEX_MODE": "silent"}),
                          ("error", {"FAKE_CODEX_MODE": "error"})):
            with self.subTest(name):
                self.stand_in(MASTACK_MODELS=table, **env)
                shutil.rmtree(self.tmp / "state", ignore_errors=True)
                self.assertIsNone(self.decide({"command": "codex exec 'review'"}))

    def test_legacy_table_hung_shim_is_stopped_and_failed_read_kept(self):
        table = self.write_table(LEGACY_CODEX_TABLE)
        self.stand_in(used=100, shim=True, FAKE_CODEX_MODE="hang", MASTACK_MODELS=table)
        self.assertIsNone(self.decide({"command": "codex exec 'review'"}))
        self.assertEqual(fake_codex.alive(self.codex_log), [])
        stored = json.loads((self.tmp / "state" / "codex-limit.json").read_text())
        self.assertIn("gave no rate limits", stored["error"])
        self.assertIsNone(self.decide({"command": "codex exec 'again'"}))
        self.assertEqual(self.reads(), 1)

    def test_legacy_table_without_codex_threshold_reads_no_quota(self):
        table = self.write_table(
            'schema = 1\n'
            'active_families = ["anthropic", "openai"]\n'
            '[models.opus]\nid = "claude-opus-test"\nfamily = "anthropic"\ncli = "claude"\n'
            '[cli.codex]\nrun = ["codex", "exec"]\n'
            '[roles.review]\nchoices = [{ model = "opus" }]\n'
        )
        self.stand_in(used=100, MASTACK_MODELS=table)
        self.assertIsNone(self.decide({"command": "codex exec 'review'"}))
        self.assertEqual(self.reads(), 0)

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("codex_credits.py")
        self.assertIsNone(self.decide({"command": "codex exec \"unterminated"}))


if __name__ == "__main__":
    unittest.main()
