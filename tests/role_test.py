#!/usr/bin/env python3
"""`bin/role`: which model takes a role now, by models.toml and the live quotas its conditions name.

A stand-in `codex` (tests/fake_codex.py) answers the quota read; the state directory is scratch. Nothing reads the
real quota or starts the real CLI.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROLE = ROOT / "bin" / "role"
TABLE = tomllib.loads((ROOT / "models.toml").read_text())
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "tests"))

import fake_codex  # noqa: E402
import hook_io  # noqa: E402
import model_roles  # noqa: E402


def model_id(name: str) -> str:
    return TABLE["models"][name]["id"]


class RoleCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="mastack-role-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        fake_codex.install(self.tmp / "bin")
        (self.tmp / "config").mkdir()
        self.log = self.tmp / "codex.log"
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("MASTACK_", "FAKE_CODEX_")) and k != "XDG_STATE_HOME"}
        self.env.update(PATH=f"{self.tmp / 'bin'}:/usr/bin:/bin", HOME=str(self.tmp), FAKE_CODEX_LOG=str(self.log),
                        MASTACK_CONFIG=str(self.config_dir), MASTACK_HOOK_STATE=str(self.tmp / "state"))

    @property
    def config_dir(self) -> pathlib.Path:
        return self.tmp / "config"

    def role(self, *args: str, used: float | None = None, **env: str) -> subprocess.CompletedProcess:
        environment = {**self.env, **env}
        if used is not None:
            environment["FAKE_CODEX_USED"] = str(used)
        return subprocess.run([sys.executable, str(ROLE), *args], capture_output=True, text=True, env=environment,
                              timeout=60)

    def answer(self, *args: str, **kwargs) -> dict:
        proc = self.role(*args, "--json", **kwargs)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        return json.loads(proc.stdout)

    def table(self, text: str) -> str:
        path = self.tmp / "models.toml"
        path.write_text(text)
        return str(path)

    def spawns(self) -> int:
        return len(self.log.read_text().splitlines()) if self.log.exists() else 0


class ResolveTests(RoleCase):
    def test_an_exhausted_weekly_limit_moves_review_to_the_same_family_fallback_with_its_note(self):
        proc = self.role("review", "--implementer-family", "anthropic", used=100)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout
        self.assertIn(model_id("opus"), out)
        self.assertIn("same family as the implementer: fresh context only", out)
        self.assertIn("sol: codex_weekly 0% left, needs 15%", out)
        self.assertIn("opus: same family as the implementer (anthropic)", out)
        self.assertIn(f"claude -p --model {model_id('opus')} --effort medium", out)

    def test_a_weekly_limit_with_room_gives_review_to_sol_with_its_command(self):
        answer = self.answer("review", "--implementer-family", "anthropic", used=50)
        self.assertEqual((answer["model"], answer["id"], answer["family"], answer["effort"]),
                         ("sol", model_id("sol"), "openai", "medium"))
        self.assertEqual(answer["argv"]["run"][:2], ["codex", "exec"])
        self.assertIn(f'model="{model_id("sol")}"', answer["argv"]["run"])
        self.assertIn('model_reasoning_effort="medium"', answer["argv"]["run"])
        self.assertEqual(answer["argv"]["review"][:2], ["codex", "review"])
        self.assertEqual(answer["skipped"], [])
        self.assertEqual(answer["quotas"]["codex_weekly"]["left"], 50)
        self.assertIsNone(answer["note"])

    def test_the_other_family_takes_the_second_choice_without_the_note(self):
        answer = self.answer("review", "--implementer-family", "openai", used=100)
        self.assertEqual((answer["model"], answer["note"]), ("opus", None))
        self.assertEqual([s["model"] for s in answer["skipped"]], ["sol"])

    def test_the_threshold_itself_qualifies(self):
        self.assertEqual(self.answer("routine", used=85)["model"], "sol")
        self.assertEqual(self.answer("routine", used=85.5)["model"], "opus")

    def test_a_missing_codex_counts_as_not_met_and_is_named(self):
        answer = self.answer("routine", PATH="/usr/bin:/bin")
        self.assertEqual(answer["model"], "opus")
        self.assertIn("sol: codex_weekly unreadable (codex is not on PATH), needs 15%", answer["skipped"][0]["reason"])

    def test_a_silent_or_failing_codex_counts_as_not_met_and_is_named(self):
        for mode, says in (("silent", "codex app-server gave no rate limits"), ("error", "not logged in")):
            with self.subTest(mode):
                reason = self.answer("routine", FAKE_CODEX_MODE=mode)["skipped"][0]["reason"]
                self.assertIn("codex_weekly unreadable", reason)
                self.assertIn(says, reason)

    def test_a_reached_limit_is_not_met_even_with_room_left(self):
        answer = self.answer("routine", used=40, FAKE_CODEX_REACHED="rate_limit_reached")
        self.assertEqual(answer["model"], "opus")
        self.assertIn("Codex reports rate_limit_reached", answer["skipped"][0]["reason"])

    def test_a_first_choice_without_conditions_reads_no_quota(self):
        answer = self.answer("implement", used=100)
        self.assertEqual((answer["model"], answer["effort"]), ("opus", "medium"))
        self.assertEqual(self.spawns(), 0)

    def test_each_quota_is_read_once(self):
        path = self.table(TABLE_HEAD + '[roles.r]\nchoices = [\n'
                          '  { model = "sol", effort = "xhigh", when = { limit = { codex_weekly = 30 } } },\n'
                          '  { model = "sol", effort = "low", when = { limit = { codex_weekly = 15 } } },\n'
                          '  { model = "opus", effort = "high" },\n]\n')
        answer = self.answer("r", MASTACK_MODELS=path, used=80)
        self.assertEqual((answer["model"], answer["effort"]), ("sol", "low"))
        self.assertEqual(self.spawns(), 1)

    def test_an_unknown_implementer_family_does_not_meet_not_family(self):
        answer = self.answer("review", used=50)
        self.assertEqual(answer["model"], "opus")
        self.assertIsNotNone(answer["note"])
        self.assertIn("--implementer-family", answer["skipped"][0]["reason"])

    def test_only_families_skips_the_other_family(self):
        path = self.table(TABLE_HEAD + '[roles.visual]\nonly_families = ["anthropic"]\n'
                          'choices = [{ model = "sol", effort = "high" }, { model = "opus", effort = "high" }]\n')
        answer = self.answer("visual", MASTACK_MODELS=path)
        self.assertEqual(answer["model"], "opus")
        self.assertEqual(answer["skipped"], [{"model": "sol", "reason": "sol: the visual role takes only anthropic"}])

    def test_no_qualifying_choice_exits_non_zero_with_every_reason(self):
        path = self.table(TABLE_HEAD + '[roles.routine]\n'
                          'choices = [{ model = "sol", effort = "medium", when = { limit = { codex_weekly = 15 } } }]\n')
        proc = self.role("routine", MASTACK_MODELS=path, used=100)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no choice qualifies", proc.stdout + proc.stderr)
        self.assertIn("sol: codex_weekly 0% left, needs 15%", proc.stdout + proc.stderr)

    def test_an_unreadable_table_or_unknown_role_exits_non_zero(self):
        for name, path, role in (("missing", str(self.tmp / "none.toml"), "review"),
                                 ("not toml", self.table("roles = ["), "review"),
                                 ("unknown condition", self.table(
                                     TABLE_HEAD + '[roles.r]\nchoices = [{ model = "opus", effort = "high", '
                                     'when = { mood = 1 } }]\n'), "r"),
                                 ("unknown model", self.table(TABLE_HEAD + '[roles.r]\nchoices = [{ model = "x" }]\n'),
                                  "r"),
                                 ("unknown role", str(ROOT / "models.toml"), "nonesuch")):
            with self.subTest(name):
                proc = self.role(role, MASTACK_MODELS=path)
                self.assertEqual(proc.returncode, 2, proc.stdout)
                self.assertTrue(proc.stderr.strip())

    def test_the_read_is_stored_for_the_hook(self):
        self.answer("routine", used=90)
        stored = json.loads((self.tmp / "state" / "codex-limit.json").read_text())
        self.assertEqual(stored["left"], 10)


class QuotaReadTests(RoleCase):
    """The quota read in process, as the hook calls it."""

    def setUp(self):
        super().setUp()
        self.saved = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)
        os.environ.pop("FAKE_CODEX_MODE", None)
        hook_io._config = None
        self.addCleanup(self.restore)

    def restore(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for key in ("FAKE_CODEX_MODE", "FAKE_CODEX_USED"):
            os.environ.pop(key, None)
        hook_io._config = None

    def test_a_hanging_codex_is_cut_off_at_the_timeout(self):
        os.environ["FAKE_CODEX_MODE"] = "hang"
        started = time.monotonic()
        quota = model_roles.codex_weekly(timeout=0.5)
        self.assertLess(time.monotonic() - started, 5)
        self.assertIsNotNone(quota.error)

    def test_a_fresh_stored_read_is_reused_and_a_stale_one_read_again(self):
        os.environ["FAKE_CODEX_USED"] = "100"
        self.assertEqual(model_roles.codex_weekly(timeout=10, max_age=300).left, 0)
        os.environ["FAKE_CODEX_USED"] = "50"
        self.assertEqual(model_roles.codex_weekly(timeout=10, max_age=300).left, 0)
        self.assertEqual(self.spawns(), 1)
        cache = self.tmp / "state" / "codex-limit.json"
        stored = json.loads(cache.read_text())
        cache.write_text(json.dumps({**stored, "read_at": stored["read_at"] - 301}))
        self.assertEqual(model_roles.codex_weekly(timeout=10, max_age=300).left, 50)
        self.assertEqual(self.spawns(), 2)

    def test_a_failed_read_is_kept_only_briefly(self):
        os.environ["FAKE_CODEX_MODE"] = "silent"
        self.assertIsNotNone(model_roles.codex_weekly(timeout=10, max_age=300).error)
        self.assertIsNotNone(model_roles.codex_weekly(timeout=10, max_age=300).error)
        self.assertEqual(self.spawns(), 1)
        cache = self.tmp / "state" / "codex-limit.json"
        stored = json.loads(cache.read_text())
        cache.write_text(json.dumps({**stored, "read_at": stored["read_at"] - model_roles.FAILED_READ_SECONDS - 1}))
        os.environ.pop("FAKE_CODEX_MODE")
        self.assertIsNone(model_roles.codex_weekly(timeout=10, max_age=300).error)


TABLE_HEAD = '''schema = 1
[models.opus]
id = "claude-opus-test"
family = "anthropic"
cli = "claude"
[models.sol]
id = "gpt-test"
family = "openai"
cli = "codex"
[cli.claude]
run = ["claude", "-p", "--model", "{id}", "--effort", "{effort}"]
[cli.codex]
run = ["codex", "exec", "-c", "model=\\"{id}\\""]
'''


if __name__ == "__main__":
    unittest.main()
