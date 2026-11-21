#!/usr/bin/env python3
"""Tests for hooks/codex_credits.py."""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import sys
import tomllib
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fake_codex  # noqa: E402
from hook_test_support import HookCase, ROOT, fixture  # noqa: E402


class CodexCreditsTests(HookCase):
    """A headless Codex run is refused while the weekly limit is below the review role's threshold. A stand-in
    codex (tests/fake_codex.py) reports the limit; nothing starts the real CLI."""

    cases = fixture("codex-credits.json")
    models = tomllib.loads((ROOT / "models.toml").read_text())

    def stand_in(self, used: float | None = 100, shim: bool = False, **env: str):
        """codex on PATH reporting `used` percent of the weekly limit; None: no codex at all."""
        self.codex_log = self.tmp / "codex.log"
        fake_codex.install(self.tmp / "codex-bin", shim=shim)
        keep = {k: self.env[k] for k in ("HOME", "MASTACK_CONFIG", "MASTACK_HOOK_STATE")}
        self.env = fake_codex.environment(self.env, self.tmp / "codex-bin" if used is not None else None,
                                          self.codex_log, FAKE_CODEX_USED=str(used or 0), **keep, **env)

    def decide(self, case, script="codex_credits.py"):
        if not getattr(self, "codex_log", None):
            self.stand_in()
        return self.bash(script, case["command"], case.get("cwd", "{home}/app"))

    def reads(self) -> int:
        return fake_codex.reads(self.codex_log) if getattr(self, "codex_log", None) else 0

    @classmethod
    def expect(cls, test, case, reason):
        opus = cls.models["models"]["opus"]["id"]
        test.assertIn("codex-credits denied", reason)
        test.assertIn("0% left", reason)
        test.assertIn("needs 15%", reason)
        test.assertIn(f"`{ROOT / 'bin' / 'role'} review` picks opus ({opus}), effort medium", reason)
        test.assertIn("reads it again", reason)
        test.assertIn(f"claude -p --model {opus} --effort medium", reason)
        test.assertIn("MASTACK_ALLOW_CREDITS=1", reason)

    def test_a_headless_run_on_an_exhausted_limit_is_denied_with_the_fallback_and_the_override(self):
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.expect(self, case, self.denied(self.decide(case)))

    def test_mentions_help_and_the_owners_override_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case))

    def test_a_limit_with_room_passes(self):
        self.stand_in(used=50)
        self.assertIsNone(self.decide({"command": "codex exec 'review'"}))

    def test_a_reached_limit_is_denied_even_with_room_left(self):
        self.stand_in(used=40, FAKE_CODEX_REACHED="rate_limit_reached")
        self.assertIn("Codex reports rate_limit_reached", self.denied(self.decide({"command": "codex exec x"})))

    def test_a_missing_silent_or_failing_codex_passes_without_a_word(self):
        for name, env in (("missing", {"used": None}), ("silent", {"FAKE_CODEX_MODE": "silent"}),
                          ("error", {"FAKE_CODEX_MODE": "error"})):
            with self.subTest(name):
                self.stand_in(**env)
                shutil.rmtree(self.tmp / "state", ignore_errors=True)
                self.assertIsNone(self.decide({"command": "codex exec 'review'"}))

    def test_the_read_is_reused_for_a_few_minutes(self):
        self.stand_in(used=100)
        self.denied(self.decide({"command": "codex exec one"}))
        self.denied(self.decide({"command": "codex exec two"}))
        self.assertEqual(self.reads(), 1)
        self.stand_in(used=50)
        cache = self.tmp / "state" / "codex-limit.json"
        stored = json.loads(cache.read_text())
        cache.write_text(json.dumps({**stored, "read_at": stored["read_at"] - 600}))
        self.assertIsNone(self.decide({"command": "codex exec three"}))
        self.assertEqual(self.reads(), 2)

    def test_a_command_that_runs_no_model_reads_no_quota(self):
        self.stand_in(used=100)
        for case in self.cases["allow"]:
            self.decide(case)
        self.assertEqual(self.reads(), 0)

    def test_the_override_is_logged_without_the_prompt(self):
        self.stand_in(used=100)
        self.assertIsNone(self.decide({"command": "MASTACK_ALLOW_CREDITS=1 codex exec 'secret prompt text'"}))
        logged = (self.tmp / "state" / "guard.log").read_text()
        self.assertIn("codex-credits override: codex exec", logged)
        self.assertNotIn("secret prompt text", logged)

    def test_a_hung_shim_is_stopped_and_its_failed_read_kept(self):
        """The npm package's codex is a Node shim that does not pass SIGKILL on to the server it started."""
        self.stand_in(used=100, shim=True, FAKE_CODEX_MODE="hang")
        self.assertIsNone(self.decide({"command": "codex exec 'review'"}))
        self.assertEqual(fake_codex.alive(self.codex_log), [])
        stored = json.loads((self.tmp / "state" / "codex-limit.json").read_text())
        self.assertIn("gave no rate limits", stored["error"])
        self.assertIsNone(self.decide({"command": "codex exec 'again'"}))
        self.assertEqual(self.reads(), 1)

    def test_a_table_without_a_codex_threshold_reads_no_quota(self):
        table = self.tmp / "models.toml"
        table.write_text(re.sub(r"(?s)\[roles\.review\].*?\]\n\n", "[roles.review]\nchoices = [{ model = \"opus\" }]\n\n",
                                (ROOT / "models.toml").read_text()))
        self.stand_in(used=100, MASTACK_MODELS=str(table))
        self.assertIsNone(self.decide({"command": "codex exec 'review'"}))
        self.assertEqual(self.reads(), 0)

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("codex_credits.py")
        self.assertIsNone(self.decide({"command": "codex exec \"unterminated"}))


if __name__ == "__main__":
    unittest.main()
