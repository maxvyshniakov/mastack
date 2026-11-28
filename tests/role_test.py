#!/usr/bin/env python3
"""`bin/role`: which model takes a role now, by models.toml and any live quotas its conditions name.

A stand-in `codex` (tests/fake_codex.py) answers quota reads for custom-table tests; the state directory is scratch.
Nothing reads the real quota or starts the real CLI.
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
    def test_real_table_routes_every_role_with_zero_codex_spawns(self):
        expected = [
            ("implement", [], ("neon", "google", "medium", "thought_level")),
            ("implement", ["--exclude-family", "google"], ("opus", "anthropic", "medium", "effort")),
            ("visual", [], ("opus", "anthropic", "high", "effort")),
            ("visual", ["--exclude-family", "anthropic"], ("neon", "google", "high", "thought_level")),
            ("review", ["--implementer-family", "google"], ("fable", "anthropic", "high", "effort")),
            ("review", ["--implementer-family", "anthropic"], ("carbon", "google", "medium", "thought_level")),
            ("critique", [], ("carbon", "google", "high", "thought_level")),
            ("critique", ["--exclude-family", "google"], ("fable", "anthropic", "high", "effort")),
            ("specify", [], ("carbon", "google", "high", "thought_level")),
            ("specify", ["--exclude-family", "google"], ("fable", "anthropic", "high", "effort")),
            ("design", [], ("carbon", "google", "high", "thought_level")),
            ("audit", [], ("carbon", "google", "high", "thought_level")),
            ("scout", [], ("sonnet", "anthropic", "medium", "effort")),
            ("scout", ["--exclude-family", "anthropic"], ("flash", "google", "medium", "thought_level")),
            ("routine", [], ("sonnet", "anthropic", "medium", "effort")),
            ("routine", ["--exclude-family", "anthropic"], ("argon", "google", "medium", "thought_level")),
            ("research", [], ("argon", "google", "medium", "thought_level")),
            ("research", ["--exclude-family", "google"], ("sonnet", "anthropic", "medium", "effort")),
        ]
        for role_name, extra_args, want in expected:
            with self.subTest(role=role_name, extra=extra_args):
                ans = self.answer(role_name, *extra_args, used=100)
                self.assertEqual((ans["model"], ans["family"], ans["effort"], ans["option"]), want)
        self.assertEqual(self.spawns(), 0)

    def test_cross_family_review_and_same_family_fallback(self):
        # Google implementer -> plain Fable (high), no note.
        ans_google = self.answer("review", "--implementer-family", "google")
        self.assertEqual((ans_google["model"], ans_google["id"], ans_google["family"], ans_google["effort"],
                          ans_google["note"]),
                         ("fable", model_id("fable"), "anthropic", "high", None))
        self.assertIn("carbon: same family as the implementer (google)", ans_google["skipped"][0]["reason"])
        self.assertEqual(ans_google["argv"]["review"],
                         ["claude", "-p", "--model", model_id("fable"), "--effort", "high"])

        # Anthropic implementer -> Carbon (medium), no note.
        ans_anth = self.answer("review", "--implementer-family", "anthropic")
        self.assertEqual((ans_anth["model"], ans_anth["id"], ans_anth["family"], ans_anth["effort"],
                          ans_anth["note"]),
                         ("carbon", model_id("carbon"), "google", "medium", None))

        # Anthropic implementer with Google excluded -> same-family Fable with fresh-context note.
        proc = self.role("review", "--implementer-family", "anthropic", "--exclude-family", "google")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout
        self.assertIn(model_id("fable"), out)
        self.assertIn("same family as the implementer: fresh context only", out)
        self.assertIn(f"claude -p --model {model_id('fable')} --effort high", out)

        # Google implementer with Anthropic excluded -> same-family Carbon with fresh-context note.
        ans_same_google = self.answer("review", "--implementer-family", "google", "--exclude-family", "anthropic")
        self.assertEqual(ans_same_google["model"], "carbon")
        self.assertIn("same family as the implementer", ans_same_google["note"])
        self.assertEqual(self.spawns(), 0)

    def test_pair_resolves_two_distinct_active_families_and_exits_1_when_only_one_remains(self):
        pair = self.answer("critique", "--pair")
        self.assertEqual((pair["primary"]["model"], pair["primary"]["effort"], pair["primary"]["family"]),
                         ("carbon", "high", "google"))
        self.assertEqual((pair["partner"]["model"], pair["partner"]["effort"], pair["partner"]["family"]),
                         ("fable", "high", "anthropic"))
        self.assertEqual(pair["skipped"], [])
        self.assertNotIn("error", pair)

        # Text format names both primary and partner.
        proc_text = self.role("critique", "--pair")
        self.assertEqual(proc_text.returncode, 0, proc_text.stderr)
        self.assertIn("critique (pair):", proc_text.stdout)
        self.assertIn("primary: carbon", proc_text.stdout)
        self.assertIn("partner: fable", proc_text.stdout)

        # T3 harness includes launch targets for both members.
        pair_t3 = self.answer("critique", "--pair", "--harness", "t3")
        self.assertEqual(pair_t3["primary"]["launch"]["target"]["driverKind"], "antigravity")
        self.assertEqual(pair_t3["partner"]["launch"]["target"]["driverKind"], "claudeAgent")

        # --family applies to primary only; partner still resolves from a distinct active family.
        pair_google = self.answer("critique", "--pair", "--family", "google")
        self.assertEqual((pair_google["primary"]["model"], pair_google["primary"]["family"]), ("carbon", "google"))
        self.assertEqual((pair_google["partner"]["model"], pair_google["partner"]["family"]), ("fable", "anthropic"))

        pair_anth = self.answer("critique", "--pair", "--family", "anthropic")
        self.assertEqual((pair_anth["primary"]["model"], pair_anth["primary"]["family"]), ("fable", "anthropic"))
        self.assertEqual((pair_anth["partner"]["model"], pair_anth["partner"]["family"]), ("carbon", "google"))

        # Excluding google leaves only anthropic -> exit 1 naming missing second family.
        proc_missing = self.role("critique", "--pair", "--exclude-family", "google", "--json")
        self.assertEqual(proc_missing.returncode, 1)
        missing = json.loads(proc_missing.stdout)
        self.assertEqual(missing["primary"]["model"], "fable")
        self.assertIsNone(missing["partner"])
        self.assertIn("no second family qualifies", missing["error"])
        self.assertIn("missing google", missing["error"])
        self.assertIn("anthropic", missing["error"])

        proc_missing_text = self.role("critique", "--pair", "--exclude-family", "google")
        self.assertEqual(proc_missing_text.returncode, 1)
        self.assertIn("missing google", proc_missing_text.stdout)

        # Review --pair with implementer-family pairs cross-family primary + fresh-context partner.
        rev_pair = self.answer("review", "--pair", "--implementer-family", "google")
        self.assertEqual((rev_pair["primary"]["model"], rev_pair["primary"]["family"], rev_pair["primary"]["note"]),
                         ("fable", "anthropic", None))
        self.assertEqual((rev_pair["partner"]["model"], rev_pair["partner"]["family"]), ("carbon", "google"))
        self.assertIn("same family as the implementer", rev_pair["partner"]["note"])
        self.assertEqual(self.spawns(), 0)

    def test_load_time_validation_enforces_active_families_and_forbid_models(self):
        # Forbidden model in an economy role raises TableError (exit 2) at load time, even for another role.
        bad_forbid = self.table(
            'schema = 1\n'
            'active_families = ["anthropic"]\n'
            '[models.opus]\nid = "claude-opus-test"\nfamily = "anthropic"\ncli = "claude"\n'
            '[models.sonnet]\nid = "claude-sonnet-test"\nfamily = "anthropic"\ncli = "claude"\n'
            '[roles.implement]\nchoices = [{ model = "opus", effort = "medium" }]\n'
            '[roles.scout]\nforbid_models = ["opus"]\n'
            'choices = [{ model = "opus", effort = "medium" }, { model = "sonnet", effort = "medium" }]\n'
        )
        proc = self.role("implement", MASTACK_MODELS=bad_forbid)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("forbidden model `opus`", proc.stderr)

        # Inactive family in a role choice raises TableError (exit 2) at load time.
        bad_family = self.table(
            'schema = 1\n'
            'active_families = ["anthropic", "google"]\n'
            '[models.opus]\nid = "claude-opus-test"\nfamily = "anthropic"\ncli = "claude"\n'
            '[models.neon]\nid = "gemini-neon-test"\nfamily = "google"\ncli = "antigravity"\n'
            '[models.sol]\nid = "gpt-test"\nfamily = "openai"\ncli = "codex"\n'
            '[roles.implement]\nchoices = [{ model = "sol", effort = "medium" }]\n'
        )
        proc = self.role("implement", MASTACK_MODELS=bad_family)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("inactive family `openai`", proc.stderr)

        # Empty, duplicate, or unknown active_families is rejected.
        for label, bad_line in (
            ("empty", "active_families = []"),
            ("duplicate", 'active_families = ["anthropic", "anthropic"]'),
            ("unknown", 'active_families = ["anthropic", "antropic"]'),
        ):
            with self.subTest(active_families=label):
                bad_active = self.table(
                    f'schema = 1\n{bad_line}\n'
                    '[models.opus]\nid = "claude-opus-test"\nfamily = "anthropic"\ncli = "claude"\n'
                    '[roles.implement]\nchoices = [{ model = "opus", effort = "medium" }]\n'
                )
                proc = self.role("implement", MASTACK_MODELS=bad_active)
                self.assertEqual(proc.returncode, 2)
                self.assertIn("active_families", proc.stderr)

        # Unknown model in forbid_models is rejected.
        bad_forbid_name = self.table(
            'schema = 1\nactive_families = ["anthropic"]\n'
            '[models.sonnet]\nid = "claude-sonnet-test"\nfamily = "anthropic"\ncli = "claude"\n'
            '[roles.scout]\nforbid_models = ["opsu"]\nchoices = [{ model = "sonnet", effort = "medium" }]\n'
        )
        proc = self.role("scout", MASTACK_MODELS=bad_forbid_name)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unknown model", proc.stderr)

        # only_families disjoint from active_families is rejected.
        bad_only = self.table(
            'schema = 1\nactive_families = ["anthropic"]\n'
            '[models.opus]\nid = "claude-opus-test"\nfamily = "anthropic"\ncli = "claude"\n'
            '[roles.visual]\nonly_families = ["google"]\nchoices = [{ model = "opus", effort = "high" }]\n'
        )
        proc = self.role("visual", MASTACK_MODELS=bad_only)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("only_families", proc.stderr)

    def test_schema_is_1_and_has_no_retired_codex_or_inert_prose_fields(self):
        self.assertEqual(TABLE["schema"], 1)
        self.assertEqual(TABLE["active_families"], ["anthropic", "google"])
        self.assertNotIn("sol", TABLE["models"])
        self.assertNotIn("codex", TABLE.get("cli", {}))
        self.assertNotIn("openai", TABLE.get("providers", {}))
        self.assertNotIn("limits", TABLE)
        self.assertNotIn("sol", TABLE.get("pricing", {}))
        self.assertNotIn("clusters", TABLE)
        for model in TABLE["models"].values():
            for forbidden_key in ("brief_guard", "competencies", "strengths", "caveats"):
                self.assertNotIn(forbidden_key, model)
        for role_name in ("scout", "routine", "research"):
            self.assertEqual(set(TABLE["roles"][role_name]["forbid_models"]),
                             {"opus", "neon", "fable", "carbon"})

    def test_an_unknown_implementer_family_does_not_meet_not_family(self):
        answer = self.answer("review")
        self.assertEqual(answer["model"], "carbon")
        self.assertIsNotNone(answer["note"])
        self.assertIn("--implementer-family", answer["skipped"][0]["reason"])
        proc = self.role("review")
        self.assertIn("implementer family not given", proc.stdout)
        self.assertIn("implementer family not given", answer["caution"])
        self.assertIsNone(self.answer("review", "--implementer-family", "google")["caution"])

    def test_harness_output_and_provider_cooldown(self):
        t3 = self.answer("implement", "--harness", "t3")
        self.assertEqual(t3["launch"]["tool"], "delegate_task")
        self.assertEqual(t3["launch"]["target"]["model"], model_id("neon"))
        self.assertEqual(t3["launch"]["target"]["driverKind"], "antigravity")
        self.assertIn("thought_level", t3["launch"]["target"]["options"])

        claude = self.answer("review", "--implementer-family", "anthropic", "--harness", "claude")
        self.assertEqual(claude["model"], "fable")
        self.assertEqual(claude["launch"]["model"], "fable")
        self.assertTrue(any("requires delegate_task" in s["reason"] for s in claude["skipped"]))

        bad = self.role("--cooldown", "openai", "2h")
        self.assertEqual(bad.returncode, 2)

        proc = self.role("--cooldown", "google", "2h")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        after = self.answer("implement")
        self.assertEqual(after["model"], "opus")
        self.assertTrue(any("in cooldown" in s["reason"] for s in after["skipped"]))

        # With google in cooldown, --pair cannot find a second family.
        pair_proc = self.role("critique", "--pair")
        self.assertEqual(pair_proc.returncode, 1)
        self.assertIn("no second family qualifies", pair_proc.stdout)

        proc = self.role("--cooldown", "google", "0")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.answer("implement")["model"], "neon")

    def test_antigravity_models_resolve_with_thought_level_and_delegate_task(self):
        for role, expected_model, expected_effort in (
            ("implement", "neon", "medium"),
            ("visual", "neon", "high"),
            ("critique", "carbon", "high"),
            ("specify", "carbon", "high"),
            ("design", "carbon", "high"),
            ("audit", "carbon", "high"),
            ("scout", "flash", "medium"),
            ("routine", "argon", "medium"),
            ("research", "argon", "medium"),
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

    def test_visual_allows_anthropic_and_google_but_rejects_openai(self):
        self.assertEqual(self.answer("visual")["model"], "opus")
        self.assertEqual(self.answer("visual", "--family", "google")["model"], "neon")
        self.assertEqual(self.answer("visual", "--exclude-family", "anthropic")["model"], "neon")
        proc = self.role("visual", "--family", "openai")
        self.assertEqual(proc.returncode, 1)

    def test_provider_options_and_cache_metadata_are_defined_for_active_families(self):
        table = model_roles.load()
        expected = {
            "anthropic": ("effort", 5, 150000, 80),
            "google": ("thought_level", 60, 185000, 80),
        }
        for family, (opt, sub_ttl, reset_tok, max_turns) in expected.items():
            meta = model_roles.provider_metadata(table, family)
            self.assertEqual(meta.get("option"), opt)
            self.assertEqual(meta.get("subagent_cache_ttl_minutes"), sub_ttl)
            self.assertEqual(meta.get("reset_context_tokens"), reset_tok)
            self.assertEqual(meta.get("max_turns_before_handoff"), max_turns)
            for key in ("cache_ttl_minutes", "warm_idle_minutes", "compact_window_tokens", "warm_context_tokens"):
                self.assertIsInstance(meta.get(key), int, f"{family}.{key}")
                self.assertGreater(meta[key], 0)

    def test_custom_table_quota_conditions_and_failures(self):
        path = self.table(
            TABLE_HEAD + '[roles.routine]\nchoices = [\n'
            '  { model = "sol", effort = "medium", when = { limit = { codex_weekly = 15 } } },\n'
            '  { model = "opus", effort = "medium" },\n]\n'
        )
        self.assertEqual(self.answer("routine", MASTACK_MODELS=path, used=85)["model"], "sol")
        self.assertEqual(self.answer("routine", MASTACK_MODELS=path, used=85.5)["model"], "opus")

        missing = self.answer("routine", MASTACK_MODELS=path, PATH="/usr/bin:/bin")
        self.assertEqual(missing["model"], "opus")
        self.assertIn("sol: codex_weekly unreadable (codex is not on PATH), needs 15%", missing["skipped"][0]["reason"])

        for mode, says in (("silent", "codex app-server gave no rate limits"), ("error", "not logged in")):
            with self.subTest(mode):
                reason = self.answer("routine", MASTACK_MODELS=path, FAKE_CODEX_MODE=mode)["skipped"][0]["reason"]
                self.assertIn("codex_weekly unreadable", reason)
                self.assertIn(says, reason)

        reached = self.answer("routine", MASTACK_MODELS=path, used=40, FAKE_CODEX_REACHED="rate_limit_reached")
        self.assertEqual(reached["model"], "opus")
        self.assertIn("Codex reports rate_limit_reached", reached["skipped"][0]["reason"])

        malformed = self.role("routine", MASTACK_MODELS=path, FAKE_CODEX_MODE="malformed")
        self.assertEqual(malformed.returncode, 0, malformed.stderr)
        self.assertNotIn("Traceback", malformed.stderr)
        self.assertIn("codex_weekly unreadable", malformed.stdout)

        stored = json.loads((self.tmp / "state" / "codex-limit.json").read_text())
        self.assertIn("error", stored)

    def test_each_quota_is_read_once(self):
        path = self.table(TABLE_HEAD + '[roles.r]\nchoices = [\n'
                          '  { model = "sol", effort = "xhigh", when = { limit = { codex_weekly = 30 } } },\n'
                          '  { model = "sol", effort = "low", when = { limit = { codex_weekly = 15 } } },\n'
                          '  { model = "opus", effort = "high" },\n]\n')
        answer = self.answer("r", MASTACK_MODELS=path, used=80)
        self.assertEqual((answer["model"], answer["effort"]), ("sol", "low"))
        self.assertEqual(self.spawns(), 1)

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
