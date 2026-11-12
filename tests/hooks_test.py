#!/usr/bin/env python3
"""Replay the agent-hook fixtures against the hooks in hooks/.

Each check must fire on its recorded incidents and pass their legitimate neighbours, alone and through the
dispatcher (bash_guard.py), which must decide exactly as the checks do. Hooks run as Claude Code runs them: JSON
on stdin, decision on stdout. Everything runs in a scratch HOME and config; nothing reads the real ones.
"""
from __future__ import annotations

import json
import os
import pathlib
import pwd
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"
FIXTURES = HOOKS / "fixtures"
sys.path.insert(0, str(HOOKS))

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


# ---- one check at a time ------------------------------------------------------------------------------------------

class GitGuard:
    cases = fixture("git-guard.json")

    @staticmethod
    def expect(test, case, reason):
        for rule in case["rules"]:
            test.assertIn(f"[{rule}]", reason)
        test.assertIn("Safe:", reason)


class GitGuardTests(HookCase):
    def decide(self, case, script="git_guard.py"):
        return self.bash(script, case["command"], case["cwd"])

    def test_incident_replays_are_denied_naming_rule_and_alternative(self):
        for case in GitGuard.cases["deny"]:
            with self.subTest(case["name"]):
                GitGuard.expect(self, case, self.denied(self.decide(case)))

    def test_legitimate_neighbours_pass(self):
        for case in GitGuard.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case))

    def test_override_is_logged(self):
        case = next(c for c in GitGuard.cases["allow"] if c["name"] == "logged override")
        self.decide(case)
        log = (self.tmp / "state" / "guard.log").read_text()
        self.assertIn("owner asked to reset main", log)
        self.assertIn("reset --hard origin/main", log)

    def test_without_checkouts_only_the_rules_for_everywhere_apply(self):
        self.settings({})
        self.assertIsNone(self.bash("git_guard.py", "git reset --hard a780eb7b", "{home}/app"))
        self.assertIsNone(self.bash("git_guard.py", "git push origin main", "{home}/app"))
        self.assertIn("[stash]", self.denied(self.bash("git_guard.py", "git stash", "{home}/app")))

    def test_env_replaces_the_configured_checkouts(self):
        self.env["MASTACK_HOOK_REPOS"] = str(self.tmp / "other")
        self.assertIsNone(self.bash("git_guard.py", "git reset --hard a780eb7b", "{home}/app"))
        self.assertIn("[shared-checkout]", self.denied(self.bash("git_guard.py", "git reset --hard x", str(self.tmp / "other"))))

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("git_guard.py")


class ZshWordSplitTests(HookCase):
    cases = fixture("zsh-word-split.json")

    def decide(self, command, script="zsh_word_split.py"):
        return self.bash(script, command, "{home}")

    @staticmethod
    def expect(test, case, reason):
        test.assertIn(f"[{case['rule']}]", reason)
        test.assertIn(f"${{={case['var']}}}", reason)
        test.assertIn("array", reason)
        test.assertIn(f'"${case["var"]}"', reason, "names the quoted form for one word")

    def test_zsh_leaves_an_unquoted_scalar_whole(self):
        # The premise: zsh splits ${=var} and arrays, never a plain $var; bash splits all three.
        if not shutil.which("zsh"):
            self.skipTest("no zsh")
        script = 'v="a b"; set -- $v; print -n $#; set -- ${=v}; print -n $#; a=(a b); set -- $a; print $#'
        self.assertEqual(subprocess.run(["zsh", "-f", "-c", script], capture_output=True, text=True).stdout, "122\n")

    def test_shapes_that_do_not_split_are_denied_with_the_fix(self):
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.expect(self, case, self.denied(self.decide(case["command"])))

    def test_look_alikes_that_split_or_mean_one_word_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"]))

    def test_one_line_per_finding(self):
        reason = self.denied(self.decide("for p in \"a b\"; do set -- $p; done; for f in $files; do :; done"))
        self.assertEqual([line.split("]")[0] for line in reason.splitlines() if line.startswith("- [")],
                         ["- [set-scalar", "- [for-scalar"])

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("zsh_word_split.py")


class UnguardedSequenceTests(HookCase):
    cases = fixture("unguarded-sequence.json")

    def decide(self, command, cwd=None, script="unguarded_sequence.py"):
        return self.bash(script, command, cwd or str(self.project))

    @staticmethod
    def expect(test, case, reason):
        block = next(part for part in reason.split("\n\n") if part.startswith("unguarded-sequence denied"))
        rule, *findings = block.splitlines()
        test.assertIn("`&&`", rule)
        test.assertIn("|| exit 1" if case.get("errexit") else "set -e", rule)
        for step in case["steps"]:
            shown = f"`{test.fill(step)}"[:60]  # a long path is shortened in the message
            test.assertTrue(any(shown in line for line in findings), f"{step!r} not named in {reason}")

    def test_shells_run_the_next_step_after_a_failure(self):
        # The premise: `;` goes on after a failure, and set -e does not stop on a failure before `&&`, one a `||`
        # handler swallows, or one inside a pipeline without pipefail; with pipefail it does.
        if not shutil.which("zsh"):
            self.skipTest("no zsh")
        script = ("false; print -n a; set -e; false && true; print -n b; false || print -n c; false | true; "
                  "print -n d; true || exit 1; print e; setopt pipe_fail; false | true; print f")
        self.assertEqual(subprocess.run(["zsh", "-f", "-c", script], capture_output=True, text=True).stdout, "abcde\n")

    def test_mutating_steps_after_an_unguarded_step_are_denied_with_the_fix(self):
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.expect(self, case, self.denied(self.decide(case["command"])))

    def test_guarded_or_read_only_look_alikes_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"]))

    def test_canonical_dispatcher_guards_lanefather_global_config_promotion(self):
        command = "cd /missing; lanefather --config /tmp/project.toml promote abc --install"
        self.assertIn("lanefather --config", self.denied(self.decide(command, script="bash_guard.py")))

    def test_project_lane_wrappers_share_lanefather_semantics_only_where_declared(self):
        facts = self.project / "docs/agents/hooks.json"
        facts.write_text(json.dumps({"mutating_steps": PROJECT_STEPS, "lanefather_commands": ["tools/lane"]}))
        forms = ["tools/lane", "/work/tools/lane", "env MODE=x tools/lane",
                 "/usr/bin/env -u MODE /work/tools/lane", "python3 -B /work/tools/lane"]
        for script in ("unguarded_sequence.py", "bash_guard.py"):
            for form in forms:
                for config in ("--config /tmp/project.toml", "--config=/tmp/project.toml"):
                    with self.subTest(script=script, form=form, config=config):
                        command = f"cd /missing; {form} {config} promote abc --install"
                        self.assertIn("promote", self.denied(self.decide(command, script=script)))
                for suffix in ("--config x show lane --json", "--config=x list", "review lane", "gc --dry-run"):
                    with self.subTest(script=script, form=form, suffix=suffix):
                        self.assertIsNone(self.decide(f"cd /missing; {form} {suffix}", script=script))
        elsewhere = self.tmp / "unconfigured"
        (elsewhere / ".git").mkdir(parents=True)
        self.assertIsNone(self.decide("cd /missing; tools/lane --config x promote abc", str(elsewhere)))

    def test_project_steps_come_from_the_sessions_repository(self):
        elsewhere = self.tmp / "elsewhere"
        (elsewhere / ".git").mkdir(parents=True)
        command = "cd ..; tools/lane land 5-x"
        self.assertIn("`tools/lane land", self.denied(self.decide(command)))
        self.assertIn("`tools/lane land", self.denied(self.decide(command, str(self.project / "desktop" / "src"))))
        self.assertIsNone(self.decide(command, str(elsewhere)))
        self.assertIsNone(self.decide(command, str(self.tmp)))
        self.assertIn("`git merge", self.denied(self.decide("cd ..; git merge x", str(elsewhere))), "git is everywhere")

    def test_a_worktree_without_the_file_reads_its_main_checkout(self):
        main, worktree = self.tmp / "main", self.tmp / "lane"
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run([*git, "init", "-q", str(main)], check=True)
        subprocess.run([*git, "-C", str(main), "commit", "-q", "--allow-empty", "-m", "base"], check=True)
        subprocess.run([*git, "-C", str(main), "worktree", "add", "-q", str(worktree)], check=True, capture_output=True)
        command = "cd ..; ./deploy.sh"
        self.assertIsNone(self.decide(command, str(worktree)))
        (main / "docs" / "agents").mkdir(parents=True)
        (main / "docs" / "agents" / "hooks.json").write_text(json.dumps({"mutating_steps": ["deploy.sh"]}))
        self.assertIn("`./deploy.sh", self.denied(self.decide(command, str(worktree))))
        (worktree / "docs" / "agents").mkdir(parents=True)
        (worktree / "docs" / "agents" / "hooks.json").write_text(json.dumps({"mutating_steps": []}))
        self.assertIsNone(self.decide(command, str(worktree)), "the worktree's own file wins")

    def test_machine_steps_apply_to_every_project(self):
        self.settings({"mutating_steps": ["bin/release"]})
        self.assertIn("`bin/release", self.denied(self.decide("make; bin/release 1.0", str(self.tmp))))

    def test_machine_and_project_steps_add_up(self):
        self.settings({"mutating_steps": ["bin/release"]})
        reason = self.denied(self.decide("make; bin/release 1.0; tools/lane land 5-x"))
        self.assertIn("`bin/release", reason)
        self.assertIn("`tools/lane land", reason)

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("unguarded_sequence.py")
        self.assertIsNone(self.decide("cd $W; git merge \"unterminated"))
        (self.project / "docs" / "agents" / "hooks.json").write_text("{not json")
        self.assertIsNone(self.decide("cd ..; tools/lane land 5-x"), "an unreadable project file adds no steps")


class PgrepSelfMatchTests(HookCase):
    cases = fixture("pgrep-self-match.json")

    def decide(self, command, script="pgrep_self_match.py"):
        return self.bash(script, command, "{home}")

    @staticmethod
    def expect(test, case, reason):
        for pattern in case["patterns"]:
            test.assertIn(repr(pattern), reason)
        test.assertIn("[l]ane check X", reason)
        test.assertIn("kill -0 $pid", reason)

    def test_pgrep_f_finds_a_shell_whose_command_holds_the_pattern(self):
        # The premise: a shell running a command with the plain pattern (an earlier wait loop) is found; one
        # running the bracketed form is not, since "[x]yz" does not contain "xyz".
        marker = f"self-match-{os.getpid()}"
        bracketed = f"[{marker[0]}]{marker[1:]}"

        def found(text, pattern):
            loop = subprocess.Popen(["/bin/sh", "-c", f"sleep 30; : {text}"], start_new_session=True)
            self.addCleanup(lambda: (loop.kill(), loop.wait()))
            time.sleep(0.2)
            hits = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True).stdout.split()
            loop.kill()
            loop.wait()
            return str(loop.pid) in hits

        self.assertTrue(found(marker, marker))
        self.assertFalse(found(bracketed, bracketed))

    def test_patterns_that_match_their_own_command_are_denied_with_the_fix(self):
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.expect(self, case, self.denied(self.decide(case["command"])))

    def test_bracketed_variable_and_name_only_forms_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"]))

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("pgrep_self_match.py")
        self.assertIsNone(self.decide("pgrep -f \"unterminated"))


class ShellPitfallsTests(HookCase):
    cases = fixture("shell-pitfalls.json")

    def decide(self, command, script="shell_pitfalls.py"):
        return self.bash(script, command, "{home}")

    @staticmethod
    def expect(test, case, reason):
        test.assertIn(case["says"], reason)

    def test_gnu_forms_are_denied_naming_the_macos_form(self):
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.expect(self, case, self.denied(self.decide(case["command"])))

    def test_look_alikes_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"]))

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("shell_pitfalls.py")


# ---- the dispatcher -----------------------------------------------------------------------------------------------

class BashGuardTests(HookCase):
    """bash_guard.py runs every check in one process and decides as they do."""

    def test_every_fixture_decides_as_its_check_does(self):
        """A deny case is denied with the check's own reason; an allow case gets no block from that check (another
        check may deny it: a pipe-masked merge in an unguarded-sequence fixture is git-guard's)."""
        sets = [(GitGuardTests, GitGuard.cases, GitGuard.expect, ("git-guard denied",),
                 lambda t, c: t.decide(c, "bash_guard.py")),
                (ZshWordSplitTests, ZshWordSplitTests.cases, ZshWordSplitTests.expect, ("zsh word-split denied",),
                 lambda t, c: t.decide(c["command"], "bash_guard.py")),
                (UnguardedSequenceTests, UnguardedSequenceTests.cases, UnguardedSequenceTests.expect,
                 ("unguarded-sequence denied",), lambda t, c: t.decide(c["command"], script="bash_guard.py")),
                (PgrepSelfMatchTests, PgrepSelfMatchTests.cases, PgrepSelfMatchTests.expect,
                 ("pgrep-self-match denied",), lambda t, c: t.decide(c["command"], "bash_guard.py")),
                (ShellPitfallsTests, ShellPitfallsTests.cases, ShellPitfallsTests.expect,
                 ("macOS has no", "BSD cat"), lambda t, c: t.decide(c["command"], "bash_guard.py"))]
        for kind, cases, expect, mine, decide in sets:
            runner = kind()
            runner.__dict__.update(self.__dict__)
            for case in cases["deny"]:
                with self.subTest(f"{kind.__name__}: {case['name']}"):
                    expect(self, case, self.denied(decide(runner, case)))
            for case in cases["allow"]:
                with self.subTest(f"{kind.__name__}: {case['name']}"):
                    output = decide(runner, case)
                    blocks = output["hookSpecificOutput"]["permissionDecisionReason"].split("\n\n") if output else []
                    self.assertFalse([b for b in blocks if b.startswith(mine)], blocks)

    def test_a_command_two_checks_deny_names_both(self):
        reason = self.denied(self.bash("bash_guard.py", "cd x; git push origin main", "{home}/app"))
        self.assertIn("[push-by-name]", reason)
        self.assertIn("unguarded-sequence denied", reason)

    def test_a_plain_command_loads_no_parser(self):
        probe = ("import json, sys; sys.path.insert(0, sys.argv[1]); import bash_guard; "
                 "bash_guard.decide({'tool_input': {'command': sys.argv[2]}}); "
                 "print(json.dumps(sorted(m for m in sys.modules if m.endswith(('_guard', '_sequence', '_split', "
                 "'_match', '_pitfalls')))))")
        loaded = lambda command: json.loads(subprocess.run([sys.executable, "-c", probe, str(HOOKS), command],
                                                           capture_output=True, text=True, env=self.env).stdout)
        self.assertEqual(loaded("ls -la"), ["bash_guard", "shell_pitfalls"])
        self.assertEqual(loaded("cd x && git status"), ["bash_guard", "git_guard", "shell_pitfalls"])

    def test_a_failing_check_is_logged_and_the_others_still_decide(self):
        import bash_guard
        import git_guard
        import hook_io
        with mock.patch.dict(os.environ, {"MASTACK_HOOK_STATE": str(self.tmp / "state")}), \
                mock.patch.object(git_guard, "check", side_effect=RuntimeError("boom")):
            hook_io_reset()
            decision = bash_guard.decide({"tool_input": {"command": "cd x; git commit -qm wip"}, "cwd": str(self.tmp)})
        hook_io_reset()
        self.assertEqual(decision[0], "deny")
        self.assertIn("unguarded-sequence denied", decision[1])
        self.assertIn("git-guard error RuntimeError('boom')", (self.tmp / "state" / "guard.log").read_text())

    def test_the_lease_guard_is_skipped_once_a_check_denied(self):
        import bash_guard
        import lease_guard
        with mock.patch.object(lease_guard, "check") as lease:
            decision = bash_guard.decide({"tool_input": {"command": "git stash; kill 12345"}, "cwd": str(self.tmp)})
        hook_io_reset()
        self.assertIn("[stash]", decision[1])
        lease.assert_not_called()

    def test_a_spent_budget_answers_with_what_was_found(self):
        import bash_guard
        import lease_guard
        import unguarded_sequence
        import zsh_word_split
        slow = lambda data: time.sleep(0.3)
        with mock.patch.dict(os.environ, {"MASTACK_HOOK_STATE": str(self.tmp / "state")}), \
                mock.patch.object(zsh_word_split, "check", side_effect=slow), \
                mock.patch.object(unguarded_sequence, "check") as later, mock.patch.object(lease_guard, "check"):
            hook_io_reset()
            decision = bash_guard.decide({"tool_input": {"command": "git stash; echo $x"}}, budget=0.2)
        hook_io_reset()
        self.assertEqual(decision[0], "deny")
        self.assertIn("[stash]", decision[1])
        later.assert_not_called()
        self.assertIn("budget spent before unguarded-sequence", (self.tmp / "state" / "guard.log").read_text())

    def test_subprocesses_get_only_what_is_left_of_the_budget(self):
        import hook_io
        import lease_guard
        hook_io.set_budget(1.0)
        self.assertLessEqual(hook_io.timeout(5), 1.0)
        hook_io.set_budget(0)
        with self.assertRaises(hook_io.OutOfTime):
            hook_io.timeout(5)
        with self.assertRaises(lease_guard.Unresolved):
            lease_guard.run(["pgrep", "-f", "x"])
        self.assertIsNone(lease_guard.status("slotfather"))
        hook_io_reset()

    def test_the_budget_fits_the_registered_timeout(self):
        import bash_guard
        import register
        self.assertEqual(register.TIMEOUT, bash_guard.HOOK_TIMEOUT)
        self.assertLess(bash_guard.BUDGET + 1.5, bash_guard.HOOK_TIMEOUT)

    def test_unreadable_or_empty_input_passes(self):
        self.assertFailsOpen("bash_guard.py")


class RegisterTests(HookCase):
    """What tests/install_test.sh cannot stage: Claude Code writing the settings while the installer runs."""

    def test_a_concurrent_write_is_kept_and_the_install_retried(self):
        import register
        settings = self.tmp / "settings.json"
        settings.write_text(json.dumps({"model": "a"}, indent=2) + "\n")
        real_render, calls = register.render, []

        def render(data, ascii_only):
            calls.append(1)
            if len(calls) == 1:  # Claude Code saves a change between our read and our write
                settings.write_text(json.dumps({"model": "a", "theme": "dark"}, indent=2) + "\n")
            return real_render(data, ascii_only)

        argv = ["register.py", "--settings", str(settings), "--config", str(self.config), "--from-worktree"]
        with mock.patch.object(register, "render", side_effect=render), mock.patch.object(sys, "argv", argv), \
                mock.patch("sys.stdout") as out:
            self.assertEqual(register.main(), 0)
        result = json.loads(settings.read_text())
        self.assertEqual(result["theme"], "dark", "the concurrent change survives")
        self.assertEqual([h["command"] for g in result["hooks"]["PreToolUse"] for h in g["hooks"]], [register.command()])
        self.assertEqual(len(calls), 2)
        self.assertIn("retry", "".join(str(call) for call in out.write.call_args_list))


class LifecycleTests(HookCase):
    """hooks/lifecycle.py and the PreToolUse observers bash_guard.py runs: they watch and never decide."""

    def recorder(self, name: str) -> str:
        """A command that appends its stdin to a file, as a lifecycle entry would get it."""
        out = self.tmp / f"{name}.jsonl"
        return f"cat >> {out} && echo >> {out}"

    def seen(self, name: str) -> list:
        path = self.tmp / f"{name}.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []

    def lifecycle(self, event: str, payload) -> subprocess.CompletedProcess:
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run([sys.executable, str(HOOKS / "lifecycle.py"), event], input=stdin, capture_output=True,
                              text=True, env=self.env, timeout=30)

    def test_each_event_runs_its_commands_with_the_event_on_stdin(self):
        self.settings({"lifecycle": {"SubagentStop": [self.recorder("stop"), self.recorder("stop2")],
                                     "SessionEnd": [self.recorder("end")]}})
        done = self.lifecycle("SubagentStop", {"hook_event_name": "SubagentStop", "agent_id": "a1"})
        self.assertEqual((0, ""), (done.returncode, done.stdout))
        self.assertEqual([{"hook_event_name": "SubagentStop", "agent_id": "a1"}], self.seen("stop"))
        self.assertEqual(1, len(self.seen("stop2")))
        self.assertEqual([], self.seen("end"))

    def test_a_failing_or_missing_command_is_logged_and_never_blocks(self):
        self.settings({"lifecycle": {"Stop": ["exit 3", "/nonexistent/tool hook", self.recorder("after")]}})
        done = self.lifecycle("Stop", {"hook_event_name": "Stop"})
        self.assertEqual((0, ""), (done.returncode, done.stdout))
        self.assertEqual(1, len(self.seen("after")), "the later command still runs")
        self.assertIn("exited 3", (self.tmp / "state" / "guard.log").read_text())

    def test_garbage_input_and_no_settings_pass(self):
        self.assertEqual((0, ""), (self.lifecycle("Stop", "not json").returncode, ""))
        self.settings({})
        self.assertEqual("", self.lifecycle("SessionEnd", {}).stdout)

    def test_bash_guard_runs_observers_only_for_their_text_and_not_after_a_deny(self):
        self.settings({"checkouts": ["~/app"], "lifecycle": {"PreToolUse": [
            {"command": self.recorder("claims"), "contains": ["junkfather"]}]}})
        self.assertIsNone(self.bash("bash_guard.py", "ls -la"))
        self.assertIsNone(self.bash("bash_guard.py", "junkfather own -- vite", tool_use_id="t1", agent_id="a1"))
        self.denied(self.bash("bash_guard.py", "junkfather own -- vite; git push origin main", "{home}/app"))
        claims = self.seen("claims")
        self.assertEqual([("junkfather own -- vite", "a1")],
                         [(c["tool_input"]["command"], c.get("agent_id")) for c in claims])

    def test_a_slow_observer_is_cut_off_and_the_command_still_passes(self):
        self.settings({"lifecycle": {"PreToolUse": [{"command": "sleep 30", "contains": ["junkfather"]}]}})
        started = time.monotonic()
        self.assertIsNone(self.bash("bash_guard.py", "junkfather list"))
        self.assertLess(time.monotonic() - started, 10)


# ---- the lease guard, with real processes -------------------------------------------------------------------------

FAKE_STATUS = r'''#!/usr/bin/env python3
"""A stand-in for `slotfather status --json [--pid PID]` serving the leases in $FAKE_QUEUE, as slotfather does."""
import json, os, subprocess, sys
queue = json.load(open(os.environ["FAKE_QUEUE"]))
args = sys.argv[1:]
if args[:2] != ["status", "--json"]:
    sys.exit(2)
public = lambda entry: {k: v for k, v in entry.items() if k not in ("env", "start_override")}
out = {"v": 1, "slots": 4, "held": len(queue), "free": 0, "legacy": []}
if args[2:3] == ["--pid"]:
    pid = int(args[3])
    found, start = [], None
    for entry in queue:
        via = "tree" if pid in entry["tree"] else "env" if pid in entry.get("env", []) else None
        if via:
            found.append({**public(entry), "via": via})
            start = entry.get("start_override") or start
    if start is None:
        ps = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                            env={**os.environ, "LC_ALL": "C"}).stdout.strip()
        start = ps or None
    out.update(entries=found, query={"pid": pid, "start": start})
else:
    out["entries"] = [public(entry) for entry in queue]
print(json.dumps(out))
'''


class LeaseGuardTests(HookCase):
    """A kill, pkill or killall that reaches another holder's slotfather lease is refused."""

    cases = fixture("lease-guard.json")

    def setUp(self):
        super().setUp()
        tag = f"lg{os.getpid() % 100000}"
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        self.worktree = self.tmp / "worktree"
        (self.worktree / ".git").mkdir(parents=True)
        (self.worktree / "desktop").mkdir()
        elsewhere = self.tmp / "elsewhere"
        (elsewhere / ".git").mkdir(parents=True)
        lanes = self.tmp / "lanes"
        lanes.mkdir()
        (lanes / "650-test.json").write_text(json.dumps({"id": "650-test", "ticket": "650", "status": "active",
                                                         "worktree": str(self.worktree)}))
        (lanes / "641-desktop-shared-host.json").write_text(json.dumps(
            {"id": "641-desktop-shared-host", "status": "active", "worktree": str(elsewhere)}))
        # Each process runs /bin/sleep under a name of its own, so pkill, killall and pgrep find only it.
        self.pids, self.markers = {}, {}
        for index, process in enumerate(self.cases["processes"]):
            marker = f"{tag}-{index:02d}-x"
            (bin_dir / marker).symlink_to("/bin/sleep")
            child = subprocess.Popen([str(bin_dir / marker), "300"], start_new_session=True)
            self.addCleanup(lambda child=child: (child.kill(), child.wait()))
            self.pids[process], self.markers[process] = child.pid, marker
        # The stand-in for the session's Claude Code process (CLAUDE_PID), with the processes started under it.
        names = [f"{tag}-s{index:02d}-x" for index, _ in enumerate(self.cases["session_children"])]
        for marker in names:
            (bin_dir / marker).symlink_to("/bin/sleep")
        session = subprocess.Popen(["/bin/sh", "-c", 'for m in "$@"; do "$m" 300 & echo $!; done; wait', "sh",
                                    *[str(bin_dir / marker) for marker in names]],
                                   stdout=subprocess.PIPE, text=True, start_new_session=True)
        self.addCleanup(lambda: (os.killpg(session.pid, 9), session.wait(), session.stdout.close()))
        for process, marker in zip(self.cases["session_children"], names):
            self.pids[process], self.markers[process] = int(session.stdout.readline()), marker
        self.pidfiles = {}
        for process, pid in self.pids.items():
            path = self.tmp / f"{process}.pid"
            path.write_text(f"{pid}\n")
            self.pidfiles[process] = path
        places = {"worktree": str(self.worktree), "elsewhere": str(elsewhere)}
        queue, self.caller_lease = [], None
        for number, (key, lease) in enumerate(self.cases["leases"].items()):
            entry = {"id": f"{number:010d}-{self.pids[lease['holder']]}", "label": lease["label"], "state": "held",
                     "count": 1, "meta": lease["meta"], "cwd": places[lease["cwd"]],
                     "lease": str(self.tmp / f"queue/{key}.json"), "pid": self.pids[lease["holder"]],
                     "pgid": self.pids[lease["holder"]], "tree": [self.pids[p] for p in lease["tree"]],
                     "env": [self.pids[p] for p in lease.get("env", [])]}
            if lease.get("start"):
                entry["start_override"] = lease["start"]
            if lease.get("caller_lease"):
                self.caller_lease = entry["lease"]
            queue.append(entry)
        (self.tmp / "queue.json").write_text(json.dumps(queue))
        (bin_dir / "slotfather").write_text(FAKE_STATUS)
        (bin_dir / "slotfather").chmod(0o755)
        self.queue = queue
        self.env.update(PATH=f"{bin_dir}:/usr/bin:/bin:/usr/sbin:/sbin", FAKE_QUEUE=str(self.tmp / "queue.json"),
                        MASTACK_LANE_RECORDS=str(lanes), SLOTFATHER_LEASE=self.caller_lease, HOME=str(self.tmp),
                        CLAUDE_PID=str(session.pid))

    def command(self, template):
        text = template
        for process, pid in self.pids.items():
            text = (text.replace(f"{{group:{process}}}", str(pid)).replace(f"{{{process}:marker}}", self.markers[process])
                    .replace(f"{{pidfile:{process}}}", str(self.pidfiles[process])))
        for process in sorted(self.pids, key=len, reverse=True):
            text = text.replace(f"{{{process}}}", str(self.pids[process]))
        self.assertNotIn("{", text, "every placeholder is filled")
        return text

    def decide(self, template, cwd=None, agent=None, script="lease_guard.py"):
        """The hook's answer for the session's main thread, or with `agent` for a subagent of it."""
        return self.run_hook(script, {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                      "cwd": cwd or str(self.worktree / "desktop"),
                                      "session_id": "session-mine", **({"agent_id": agent} if agent else {}),
                                      "tool_input": {"command": self.command(template)}})

    def assertRefused(self, output, case, decision="deny"):
        self.assertIsNotNone(output, "allowed")
        answer = output["hookSpecificOutput"]
        self.assertEqual(answer["permissionDecision"], decision)
        reason = answer["permissionDecisionReason"]
        if decision == "deny":
            self.assertIn("never to kill another holder's lease", reason)
            self.assertIn("Safe:", reason)
        else:
            self.assertIn("only the owner approves it", reason)
            self.assertNotIn("Safe:", reason)
        for label in case["leases"]:
            self.assertIn(f"lease {label} ", reason)
        for label in {lease["label"] for lease in self.cases["leases"].values()} - set(case["leases"]):
            self.assertNotIn(f"lease {label} ", reason, "only the leases it reaches are named")
        if case.get("reused"):
            self.assertIn("reused", reason)
        return reason

    def test_kills_that_reach_another_holders_lease_are_denied_naming_it(self):
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.assertRefused(self.decide(case["command"]), case)

    def test_own_leases_free_processes_and_looks_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"]))
        for child in self.pids.values():
            os.kill(child, 0)  # the guard itself signalled nothing

    def test_a_subagent_owns_only_its_lane_and_worktree_not_the_sessions_leases(self):
        for case in self.cases["subagent_deny"]:
            with self.subTest(case["name"]):
                self.assertRefused(self.decide(case["command"], agent="a1"), case,
                                   "ask" if case.get("asked") else "deny")
        for case in self.cases["subagent_allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"], agent="a1"))

    def test_an_override_asks_the_owner_on_the_permission_card_and_is_logged(self):
        for case in self.cases["asked"]:
            with self.subTest(case["name"]):
                reason = self.assertRefused(self.decide(case["command"]), case, "ask")
                self.assertIn("owner asked to stop the stuck 641 gate", reason)
        log = (self.tmp / "state" / "guard.log").read_text()
        self.assertIn("lease-guard override asked", log)
        self.assertIn("stuck 641 gate", log)
        self.assertIsNone(self.decide('LEASE_GUARD_OK="mine" kill {mine}'), "an override reaching no lease passes")

    def test_the_dispatcher_passes_the_ask_on_and_a_deny_beats_it(self):
        case = self.cases["asked"][0]
        self.assertRefused(self.decide(case["command"], script="bash_guard.py"), case, "ask")
        reason = self.denied(self.decide(case["command"] + "; git stash", script="bash_guard.py"))
        self.assertIn("[stash]", reason)
        self.assertRefused(self.decide("kill -9 {other}", script="bash_guard.py"),
                           {"leases": ["lane-641-desktop-shared-host"]})

    def test_a_broad_kill_checks_every_process_it_reaches_also_those_outside_a_tree(self):
        """Above the per-pid limit, a process that left its lease's tree and carries its SLOTFATHER_LEASE is still
        found (an earlier shortcut kept only the pids in a lease's tree)."""
        marker = f"lgbroad-{os.getpid()}"
        lease = next(entry for entry in self.queue if entry["label"] == "lane-641-desktop-shared-host")
        sleeper = [sys.executable, "-c", "import time; time.sleep(300)", marker]
        free = {k: v for k, v in self.env.items() if k != "SLOTFATHER_LEASE"}
        children = [subprocess.Popen(sleeper, start_new_session=True,
                                     env={**free, "SLOTFATHER_LEASE": lease["lease"]} if index == 0 else free)
                    for index in range(60)]
        for child in children:
            self.addCleanup(lambda child=child: (child.kill(), child.wait()))
        lease["env"].append(children[0].pid)
        (self.tmp / "queue.json").write_text(json.dumps(self.queue))
        deadline = time.monotonic() + 30
        while len(subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True).stdout.split()) < 60:
            self.assertLess(time.monotonic(), deadline, "the sleepers did not start")
            time.sleep(0.05)
        reason = self.assertRefused(self.decide(f"pkill -f {marker}"), {"leases": ["lane-641-desktop-shared-host"]})
        self.assertIn(f"pid {children[0].pid}, outside its tree", reason)

    @unittest.skipUnless(sys.platform == "darwin", "macOS killall")
    def test_killall_by_user_alone_reaches_every_process_of_the_user(self):
        user = pwd.getpwuid(os.getuid()).pw_name
        self.assertRefused(self.decide(f"killall -u {user}"), {"reused": True, "leases": [
            "lane-641-desktop-shared-host", "scripts", "kit-verify"]})

    def test_another_lanes_worktree_owns_its_lease_and_not_the_callers(self):
        elsewhere = str(self.tmp / "elsewhere")
        self.assertIsNone(self.decide("kill {other}", cwd=elsewhere, agent="a1"))
        self.assertIsNotNone(self.decide("kill {mine}", cwd=elsewhere, agent="a1"))

    def test_a_configured_slotfather_off_path_is_asked(self):
        fake = os.path.join(self.env["PATH"].split(":")[0], "slotfather")
        self.env.update(PATH="/usr/bin:/bin", MASTACK_SLOTFATHER=fake)
        self.assertRefused(self.decide("kill -9 {other}"), {"leases": ["lane-641-desktop-shared-host"]})
        self.env["MASTACK_SLOTFATHER"] = str(self.tmp / "missing-slotfather")
        self.assertIsNone(self.decide("kill -9 {other}"))

    def test_without_slotfather_or_input_everything_passes(self):
        self.env["PATH"] = "/usr/bin:/bin"
        self.assertIsNone(self.decide("kill -9 {other}"))
        self.assertFailsOpen("lease_guard.py")
        self.assertIsNone(self.run_hook("lease_guard.py", {"tool_name": "Bash", "tool_input": {"command": "kill \"x"}}))


INSTALLED_SLOTFATHER = shutil.which("slotfather")


@unittest.skipUnless(INSTALLED_SLOTFATHER, "slotfather is not installed on this machine")
class InstalledLeaseGuardTests(HookCase):
    """The guard against the installed slotfather with a private queue (SLOTFATHER_DIR): its real `status --json
    --pid` answer for a lease whose metadata names a lane, and for one of the caller's own lane."""

    def setUp(self):
        super().setUp()
        self.worktree = self.tmp / "worktree"
        (self.worktree / ".git").mkdir(parents=True)
        lanes = self.tmp / "lanes"
        lanes.mkdir()
        (lanes / "650-test.json").write_text(json.dumps({"id": "650-test", "status": "active",
                                                         "worktree": str(self.worktree)}))
        (self.tmp / "memory").write_text("8000 1\n")
        self.env.update(SLOTFATHER_DIR=str(self.tmp / "queue"), SLOTFATHER_LEGACY_DIRS="", SLOTFATHER_CORES="12",
                        SLOTFATHER_LOADAVG="0", SLOTFATHER_MEMORY_FILE=str(self.tmp / "memory"),
                        SLOTFATHER_POLL="0.05", MASTACK_LANE_RECORDS=str(lanes))
        for key in [k for k in self.env if k in ("SLOTFATHER_LEASE", "SLOTFATHER_COUNT", "SLOTFATHER_YIELD")]:
            del self.env[key]

    def lease(self, lane):
        """A `slotfather run` whose child is a shell that records its own pid, then sleeps."""
        out = self.tmp / f"{lane}.pid"
        holder = subprocess.Popen([INSTALLED_SLOTFATHER, "run", "-n", "1", "--label", f"lane-{lane}", "--meta",
                                   f"lane={lane}", "--", "/bin/sh", "-c", f'echo $$ > "{out}"; exec sleep 300'],
                                  env=self.env, start_new_session=True, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (os.killpg(holder.pid, 9), holder.wait()))
        deadline = time.monotonic() + 30
        while not (out.exists() and out.read_text().strip()):
            self.assertLess(time.monotonic(), deadline, "the lease's command did not start")
            time.sleep(0.05)
        return int(out.read_text())

    def decide(self, command):
        return self.run_hook("lease_guard.py", {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                                "cwd": str(self.worktree), "session_id": "s", "agent_id": "a1",
                                                "tool_input": {"command": command}})

    def test_the_real_queue_answer_denies_another_lane_and_passes_the_callers(self):
        other, mine = self.lease("641-other"), self.lease("650-test")
        output = self.decide(f"kill -9 {other}")
        self.assertIsNotNone(output, "allowed")
        self.assertIn("lease lane-641-other ", output["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIn("lane 641-other", output["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(self.decide(f"kill -9 {mine}"))


if __name__ == "__main__":
    unittest.main()
