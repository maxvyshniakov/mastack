#!/usr/bin/env python3
"""Tests for hooks/lifecycle.py and PreToolUse observers/rewriters."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from hook_test_support import HOOKS, HookCase, hook_io_reset  # noqa: E402


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

    def test_observers_get_only_what_the_checks_left_of_the_budget(self):
        import lifecycle
        self.settings({"lifecycle": {"PreToolUse": [{"command": self.recorder("late"), "contains": ["junkfather"]}]}})
        data = {"tool_name": "Bash", "tool_input": {"command": "junkfather list"}}
        with mock.patch.dict(os.environ, {"MASTACK_CONFIG": str(self.config),
                                          "MASTACK_HOOK_STATE": str(self.tmp / "state")}):
            hook_io_reset()
            lifecycle.observe(data, left=0.05)
            hook_io_reset()
        self.assertEqual([], self.seen("late"))
        self.assertIn("spent the budget", (self.tmp / "state" / "guard.log").read_text())

    def rewriter(self, prefix: str = "echo rewritten") -> str:
        """A rewriter as a tool would register it: it answers with the call's input, its command prefixed."""
        script = self.tmp / "rewriter.py"
        script.write_text("import json, sys\n"
                          "data = json.load(sys.stdin)\n"
                          f"data['tool_input']['command'] = {prefix!r} + '\\n' + data['tool_input']['command']\n"
                          "print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',"
                          " 'updatedInput': data['tool_input']}}))\n")
        return f"{sys.executable} {script}"

    def background(self, command: str, background: bool = True, cwd: str | None = None):
        return self.bash("bash_guard.py", command, cwd, tool_use_id="t1",
                         tool_input={"command": self.fill(command), "run_in_background": background,
                                     "description": "kept"})

    def test_a_rewriter_answers_for_background_calls_beside_the_observers(self):
        self.settings({"checkouts": ["~/app"], "lifecycle": {"PreToolUse": [
            {"command": self.rewriter(), "background": True, "rewrite": True},
            {"command": self.recorder("seen"), "contains": ["sleep"]}]}})
        output = self.background("sleep 600")
        self.assertEqual({"hookEventName": "PreToolUse",
                          "updatedInput": {"command": "echo rewritten\nsleep 600", "run_in_background": True,
                                           "description": "kept"}}, output["hookSpecificOutput"],
                         "no permission decision of its own: Claude Code's rules judge the rewritten call")
        self.assertEqual(["sleep 600"], [c["tool_input"]["command"] for c in self.seen("seen")],
                         "observers see the agent's command")
        self.assertIsNone(self.background("sleep 600", background=False), "a foreground call is not rewritten")
        self.denied(self.background("git push origin main; sleep 600", cwd="{home}/app"))

    def test_a_check_that_asks_keeps_its_question_beside_the_rewrite(self):
        import bash_guard
        self.settings({"lifecycle": {"PreToolUse": [{"command": self.rewriter(), "background": True,
                                                     "rewrite": True}]}})
        data = {"tool_name": "Bash", "tool_input": {"command": "sleep 1", "run_in_background": True}}
        with mock.patch.dict(os.environ, {"MASTACK_CONFIG": str(self.config)}), \
                mock.patch.object(bash_guard, "decide", return_value=("ask", "owner decides")):
            hook_io_reset()
            answer = bash_guard.guard(data)
            hook_io_reset()
        self.assertEqual((("ask", "owner decides"), "echo rewritten\nsleep 1"),
                         (answer.decision, answer.updated_input["command"]))

    def test_a_rewriter_that_fails_or_answers_nonsense_leaves_the_call_alone(self):
        for command in ("exit 3", "echo not json", "echo '{\"hookSpecificOutput\": {\"updatedInput\": {}}}'",
                        "sleep 30", "/nonexistent/rewriter"):
            with self.subTest(command=command):
                self.settings({"lifecycle": {"PreToolUse": [{"command": command, "rewrite": True}]}})
                started = time.monotonic()
                self.assertIsNone(self.background("sleep 600"))
                self.assertLess(time.monotonic() - started, 9)
        self.assertIn("lifecycle rewrite", (self.tmp / "state" / "guard.log").read_text())

    def test_what_a_timed_out_entry_left_running_is_killed_with_it(self):
        marker = f"{os.getpid() % 1000 + 6000}.5"  # a sleep this test alone runs
        self.settings({"lifecycle": {"PreToolUse": [
            {"command": f"sleep {marker} & wait", "rewrite": True},
            {"command": f"sleep {marker}1 & wait", "contains": ["sleep"]}]}})
        self.assertIsNone(self.background("sleep 600"))
        left = subprocess.run(["ps", "-axo", "command="], capture_output=True, text=True).stdout.splitlines()
        self.assertEqual([], [line for line in left if line.strip().startswith(f"sleep {marker}")])

    def test_a_slow_observer_is_cut_off_and_the_command_still_passes(self):
        self.settings({"lifecycle": {"PreToolUse": [{"command": "sleep 30", "contains": ["junkfather"]}]}})
        started = time.monotonic()
        self.assertIsNone(self.bash("bash_guard.py", "junkfather list"))
        self.assertLess(time.monotonic() - started, 10)


if __name__ == "__main__":
    unittest.main()
