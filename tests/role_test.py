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
import tomllib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROLE = ROOT / "bin" / "role"
TABLE = tomllib.loads((ROOT / "models.toml").read_text())
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "tests"))

import fake_codex  # noqa: E402
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
        self.env = fake_codex.environment(os.environ, self.tmp / "bin", self.log, HOME=str(self.tmp),
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
        return fake_codex.reads(self.log)


class ResolveTests(RoleCase):
    def test_an_exhausted_weekly_limit_moves_review_to_another_family_then_same_family_fallback(self):
        cross = self.answer("review", "--implementer-family", "anthropic", used=100)
        self.assertEqual((cross["model"], cross["family"], cross["note"]), ("carbon", "google", None))
        self.assertIn("sol: codex_weekly 0% left, needs 15%", cross["skipped"][0]["reason"])
        self.assertIn("opus: same family as the implementer (anthropic)", cross["skipped"][1]["reason"])

        proc = self.role("review", "--implementer-family", "anthropic", "--exclude-family", "google", used=100)
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

    def test_scouting_goes_to_sol_while_codex_has_its_threshold_left_then_to_sonnet(self):
        answer = self.answer("scout", used=85)
        self.assertEqual((answer["model"], answer["effort"]), ("sol", "medium"))
        self.assertEqual(answer["argv"]["run"][:2], ["codex", "exec"])
        answer = self.answer("scout", used=86)
        self.assertEqual((answer["model"], answer["id"], answer["effort"]), ("sonnet", model_id("sonnet"), "medium"))
        self.assertIn("sol: codex_weekly 14% left, needs 15%", answer["skipped"][0]["reason"])

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

    def test_without_the_implementer_family_the_answer_says_so(self):
        proc = self.role("review", used=50)
        self.assertIn("implementer family not given", proc.stdout)
        self.assertIn("implementer family not given", self.answer("review", used=50)["caution"])
        self.assertIsNone(self.answer("review", "--implementer-family", "openai", used=50)["caution"])

    def test_a_malformed_answer_is_named_without_a_traceback(self):
        proc = self.role("routine", FAKE_CODEX_MODE="malformed")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("codex_weekly unreadable", proc.stdout)

    def test_harness_output_and_provider_cooldown(self):
        t3 = self.answer("scout", "--harness", "t3", used=50)
        self.assertEqual(t3["launch"]["tool"], "delegate_task")
        self.assertEqual(t3["launch"]["target"]["model"], model_id("sol"))
        self.assertEqual(t3["launch"]["target"]["driverKind"], "codex")
        self.assertIn("reasoningEffort", t3["launch"]["target"]["options"])

        claude = self.answer("review", "--implementer-family", "anthropic", "--harness", "claude", used=100)
        self.assertEqual(claude["model"], "opus")
        self.assertEqual(claude["launch"]["model"], "opus")
        self.assertTrue(any("requires delegate_task" in s["reason"] for s in claude["skipped"]))

        bad = self.role("--cooldown", "antropic", "2h")
        self.assertEqual(bad.returncode, 2)

        proc = self.role("--cooldown", "anthropic", "2h")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        after = self.answer("implement", used=50)
        self.assertEqual(after["model"], "sol")
        self.assertTrue(any("in cooldown" in s["reason"] for s in after["skipped"]))

        proc = self.role("--cooldown", "anthropic", "0")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.answer("implement", used=50)["model"], "opus")

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

    def test_antigravity_models_resolve_with_thought_level_and_delegate_task(self):
        for role, expected_model, expected_effort in (
            ("design", "neon", "high"),
            ("implement", "neon", "medium"),
            ("visual", "neon", "high"),
            ("scout", "flash", "medium"),
            ("routine", "flash", "medium"),
            ("research", "argon", "medium"),
            ("audit", "carbon", "high"),
        ):
            with self.subTest(role=role):
                answer = self.answer(role, "--family", "google")
                self.assertEqual((answer["model"], answer["id"], answer["family"], answer["cli"], answer["effort"],
                                  answer["option"]),
                                 (expected_model, model_id(expected_model), "google", "antigravity", expected_effort,
                                  "thought_level"))
                proc = self.role(role, "--family", "google")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn(
                    f'delegate_task: target.model="{model_id(expected_model)}", '
                    f'target.options.thought_level="{expected_effort}"',
                    proc.stdout,
                )

    def test_cross_family_review_routes_across_all_three_families(self):
        # Google implementer -> Sol when Codex has quota, Opus when Codex is exhausted.
        self.assertEqual(self.answer("review", "--implementer-family", "google", used=50)["model"], "sol")
        ans_exhausted = self.answer("review", "--implementer-family", "google", used=100)
        self.assertEqual((ans_exhausted["model"], ans_exhausted["note"]), ("opus", None))

        # Anthropic implementer -> Carbon when Google is selected or Anthropic is excluded and Codex is exhausted.
        ans_google = self.answer("review", "--implementer-family", "anthropic", "--family", "google", used=100)
        self.assertEqual((ans_google["model"], ans_google["family"], ans_google["option"], ans_google["note"]),
                         ("carbon", "google", "thought_level", None))
        ans_excl = self.answer("review", "--implementer-family", "anthropic", "--exclude-family", "anthropic", used=100)
        self.assertEqual((ans_excl["model"], ans_excl["family"], ans_excl["note"]), ("carbon", "google", None))

        # Google implementer cannot be reviewed by Google under not_family = true.
        proc = self.role("review", "--implementer-family", "google", "--family", "google", used=50)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("same family as the implementer (google)", proc.stdout)

    def test_visual_allows_anthropic_and_google_but_rejects_openai(self):
        self.assertEqual(self.answer("visual")["model"], "opus")
        self.assertEqual(self.answer("visual", "--family", "google")["model"], "neon")
        self.assertEqual(self.answer("visual", "--exclude-family", "anthropic")["model"], "neon")
        proc = self.role("visual", "--family", "openai")
        self.assertEqual(proc.returncode, 1)

    def test_implement_and_scout_fall_back_to_google_when_other_families_unavailable(self):
        impl = self.answer("implement", "--exclude-family", "anthropic", used=100)
        self.assertEqual((impl["model"], impl["family"], impl["option"]), ("neon", "google", "thought_level"))
        scout = self.answer("scout", "--exclude-family", "anthropic", used=100)
        self.assertEqual((scout["model"], scout["family"], scout["option"]), ("flash", "google", "thought_level"))

    def test_provider_options_and_cache_metadata_are_defined_for_all_three_families(self):
        self.assertEqual(self.answer("implement")["option"], "effort")
        self.assertEqual(self.answer("scout", used=50)["option"], "model_reasoning_effort")
        self.assertEqual(self.answer("scout", "--family", "google")["option"], "thought_level")
        table = model_roles.load()
        for family, expected_opt in (("anthropic", "effort"), ("openai", "model_reasoning_effort"),
                                     ("google", "thought_level")):
            meta = model_roles.provider_metadata(table, family)
            self.assertEqual(meta.get("option"), expected_opt)
            for key in ("cache_ttl_minutes", "warm_idle_minutes", "compact_window_tokens", "warm_context_tokens"):
                self.assertIsInstance(meta.get(key), int, f"{family}.{key}")
                self.assertGreater(meta[key], 0)


class QuotaReadTests(RoleCase):
    """The quota read in process, as the hook calls it."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, self.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        model_roles.hook_io._config = None
        self.addCleanup(setattr, model_roles.hook_io, "_config", None)

    def age(self, seconds: float, **fields):
        """Make the stored read `seconds` older, with `fields` changed."""
        cache = self.tmp / "state" / "codex-limit.json"
        stored = json.loads(cache.read_text())
        cache.write_text(json.dumps({**stored, "read_at": stored["read_at"] - seconds, **fields}))

    def test_a_hanging_codex_is_cut_off_and_its_processes_stopped(self):
        """The npm package's codex is a shim that does not pass SIGKILL on to the server it started."""
        for shim in (False, True):
            with self.subTest(shim=shim):
                fake_codex.install(self.tmp / "bin", shim=shim)
                probe = ("import sys; sys.path.insert(0, sys.argv[1]); import model_roles; "
                         "print(model_roles.codex_weekly(timeout=0.5).error)")
                proc = subprocess.run([sys.executable, "-c", probe, str(ROOT / "hooks")], capture_output=True,
                                      text=True, env={**self.env, "FAKE_CODEX_MODE": "hang"}, timeout=30)
                self.assertIn("gave no rate limits", proc.stdout, proc.stderr)
                self.assertEqual(fake_codex.alive(self.log), [])

    def test_a_result_that_is_not_an_object_is_an_unreadable_quota(self):
        os.environ["FAKE_CODEX_MODE"] = "malformed"
        self.assertIn("unexpected", model_roles.codex_weekly(timeout=10).error)

    def test_a_fresh_stored_read_is_reused_and_a_stale_one_read_again(self):
        os.environ["FAKE_CODEX_USED"] = "100"
        self.assertEqual(model_roles.codex_weekly(timeout=10, max_age=300).left, 0)
        os.environ["FAKE_CODEX_USED"] = "50"
        self.assertEqual(model_roles.codex_weekly(timeout=10, max_age=300).left, 0)
        self.assertEqual(self.spawns(), 1)
        self.age(301)
        self.assertEqual(model_roles.codex_weekly(timeout=10, max_age=300).left, 50)
        self.assertEqual(self.spawns(), 2)

    def test_a_stored_read_ends_when_the_window_resets(self):
        os.environ["FAKE_CODEX_USED"] = "100"
        self.assertEqual(model_roles.codex_weekly(timeout=10, max_age=300).left, 0)
        self.age(10, resets_at=time_now() - 1)
        os.environ["FAKE_CODEX_USED"] = "0"
        self.assertEqual(model_roles.codex_weekly(timeout=10, max_age=300).left, 100)
        self.assertEqual(self.spawns(), 2)

    def test_the_reset_time_is_stored(self):
        os.environ.update(FAKE_CODEX_USED="100", FAKE_CODEX_RESETS_AT="1900000000")
        self.assertEqual(model_roles.codex_weekly(timeout=10).resets_at, 1900000000)

    def test_a_failed_read_is_kept_only_briefly(self):
        os.environ["FAKE_CODEX_MODE"] = "silent"
        self.assertIsNotNone(model_roles.codex_weekly(timeout=10, max_age=300).error)
        self.assertIsNotNone(model_roles.codex_weekly(timeout=10, max_age=300).error)
        self.assertEqual(self.spawns(), 1)
        self.age(model_roles.FAILED_READ_SECONDS + 1)
        os.environ.pop("FAKE_CODEX_MODE")
        self.assertIsNone(model_roles.codex_weekly(timeout=10, max_age=300).error)


class SkillTests(unittest.TestCase):
    def test_every_skill_that_picks_a_model_runs_role_through_its_own_link(self):
        """`<this skill's directory>/scripts/role` works whether the path is resolved physically or by text, as an
        agent normalising `..` would, since the link sits inside the installed skill directory."""
        # `orchestration-audit` references `models.toml` for `[pricing.*]` / `[providers.*]` weights, not to pick a model.
        named = [path.parent for path in (ROOT / "skills").glob("*/SKILL.md")
                 if path.parent.name != "orchestration-audit"
                 and any(text in path.read_text() for text in ("bin/role", "scripts/role", "models.toml"))]
        self.assertGreaterEqual({p.name for p in named}, {"cross-review", "orchestrate", "research", "rate"})
        for skill in named:
            with self.subTest(skill.name):
                text = (skill / "SKILL.md").read_text()
                self.assertIn("<this skill's directory>/scripts/role", text)
                self.assertNotIn("../../bin/role", text)
                self.assertEqual((skill / "scripts" / "role").resolve(), ROLE.resolve())

    def test_every_model_has_tokenfather_pricing_weights(self):
        """`tokenfather/pricing.py` reads `[pricing.default]` and `[pricing.<alias>]` for every model."""
        required_keys = ("input", "output", "cache_read", "cache_write_short", "cache_write_long",
                         "cache_write_default", "tier_multiplier")
        pricing = TABLE.get("pricing")
        self.assertIsInstance(pricing, dict)
        self.assertIn("default", pricing)
        for alias in ("default", *TABLE["models"].keys()):
            with self.subTest(alias=alias):
                entry = pricing.get(alias)
                self.assertIsInstance(entry, dict, f"missing [pricing.{alias}] in models.toml")
                for key in required_keys:
                    val = entry.get(key)
                    self.assertIsInstance(val, (int, float), f"[pricing.{alias}].{key}")
                    self.assertNotIsInstance(val, bool)
                    self.assertGreater(val, 0, f"[pricing.{alias}].{key}")


def time_now() -> float:
    import time
    return time.time()


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
