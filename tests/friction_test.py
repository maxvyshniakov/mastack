#!/usr/bin/env python3
"""The friction journal, its TypeScript hook, the session scanner, the vendored-copy scanner and `/friction`.

Everything runs in a scratch HOME, config, journal and transcript tree; nothing reads the real ones.
"""
from __future__ import annotations

import json
import os
import pathlib
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"
FRICTION = ROOT / "bin" / "friction"
sys.path.insert(0, str(HOOKS))

import friction_journal  # noqa: E402

# repo-kit's friction schema, version 1: every writer emits exactly these fields.
SCHEMA_FIELDS = ["v", "ts", "project", "package", "kind", "component", "rule", "detail", "session", "source", "why",
                 "file", "fingerprint"]

DECLARATIONS = 'export { Button, type ButtonProps, buttonVariants } from "./button.js";\n' \
               'export { CollapsibleTrigger, Collapsible } from "./collapsible.js";\n' \
               'export { ItemDescription, ItemBody } from "./item.js";\nexport declare function useThing(): void;\n'


class FrictionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="mastack-friction-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home, self.config = self.tmp / "home", self.tmp / "config"
        for directory in (self.home, self.config):
            directory.mkdir()
        (self.tmp / "kit.d.ts").write_text(DECLARATIONS)
        self.journal = self.tmp / "journal" / "events.jsonl"
        self.app = self.home / "app"
        (self.app / ".git").mkdir(parents=True)
        (self.app / "src").mkdir()
        (self.app / "src" / "panel.tsx").write_text(
            'import { CollapsibleTrigger, type ButtonProps } from "@acme/ui-kit";\nimport { local } from "./local";\n')
        self.write_config({})
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("MASTACK_", "FRICTION_", "CLAUDE_CODE_SESSION", "CODEX_")) and k != "XDG_STATE_HOME"}
        self.env.update(HOME=str(self.home), MASTACK_CONFIG=str(self.config), FRICTION_JOURNAL=str(self.journal),
                        XDG_STATE_HOME=str(self.tmp / "state"))

    def write_config(self, extra: dict):
        base = {"scopes": ["@acme/"],
                "packages": {"@acme/ui-kit": {"aliases": ["UI Kit"], "types": [str(self.tmp / "kit.d.ts")]}}}
        (self.config / "friction.json").write_text(json.dumps({**base, **extra}))

    def config_data(self) -> dict:
        return json.loads((self.config / "friction.json").read_text())

    def events(self) -> list[dict]:
        if not self.journal.exists():
            return []
        return [json.loads(line) for line in self.journal.read_text().splitlines() if line]

    def run_friction(self, *args, check=True) -> subprocess.CompletedProcess:
        proc = subprocess.run([sys.executable, str(FRICTION), *args], capture_output=True, text=True, env=self.env,
                              cwd=self.app, timeout=60)
        if check:
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc


class JournalTests(FrictionCase):
    def test_the_journal_path_follows_friction_journal_then_the_state_directory(self):
        self.assertEqual(friction_journal.journal_path({"FRICTION_JOURNAL": "/x/j.jsonl"}), pathlib.Path("/x/j.jsonl"))
        self.assertEqual(friction_journal.journal_path({"XDG_STATE_HOME": "/s"}), pathlib.Path("/s/friction/events.jsonl"))
        self.assertIsNone(friction_journal.journal_path({"FRICTION_JOURNAL": "off"}))

    def test_events_carry_exactly_the_schema_fields_and_invalid_ones_are_not_written(self):
        good = friction_journal.event(package="@acme/ui-kit", kind="note", project="app", source="test")
        self.assertEqual(list(good), SCHEMA_FIELDS)
        bad = {**good, "kind": "bogus"}
        self.assertEqual(friction_journal.append([good, bad], {"FRICTION_JOURNAL": str(self.journal)}), 1)
        self.assertEqual([e["kind"] for e in self.events()], ["note"])
        self.assertEqual(self.journal.stat().st_mode & 0o777, 0o600)
        self.assertEqual(friction_journal.append([good], {"FRICTION_JOURNAL": str(self.journal / "x")}), 0,
                         "an unwritable journal is silent")

    def test_a_worktree_is_named_after_its_repository(self):
        worktree = self.home / "app-lane"
        worktree.mkdir()
        (self.app / ".git" / "worktrees" / "lane").mkdir(parents=True)
        (worktree / ".git").write_text(f"gitdir: {self.app / '.git' / 'worktrees' / 'lane'}\n")
        self.assertEqual(friction_journal.project_name(worktree / "src"), "app")
        self.assertEqual(friction_journal.project_name(self.app / "src"), "app")


TSC_OUTPUT = """
src/panel.tsx(4,10): error TS2322: Type '{ asChild: true; }' is not assignable to type 'IntrinsicAttributes & CollapsibleTriggerProps'.
  Property 'asChild' does not exist on type 'IntrinsicAttributes & CollapsibleTriggerProps'.
src/icons.tsx:1:10 - error TS2724: '"@acme/ui-kit/icons"' has no exported member named 'Bell'. Did you mean 'Bell2'?
src/local.ts(3,1): error TS2322: Type 'string' is not assignable to type 'LocalThing'.
src/panel.tsx(9,3): error TS2339: Property 'tone' does not exist on type 'Settings'.
"""


class TypeErrorTests(FrictionCase):
    def test_only_errors_about_a_configured_package_count_and_each_says_why(self):
        found = friction_journal.type_errors(TSC_OUTPUT, self.app, self.config_data(), session="s1", source="test")
        self.assertEqual([(e["rule"], e["component"], e["file"]) for e in found],
                         [("TS2322", "CollapsibleTrigger", "src/panel.tsx"), ("TS2724", "Bell", "src/icons.tsx")])
        self.assertIn("imports CollapsibleTrigger from @acme/ui-kit", found[0]["why"])
        self.assertIn("names @acme/ui-kit/icons", found[1]["why"])
        self.assertEqual({e["package"] for e in found}, {"@acme/ui-kit"})
        self.assertEqual(found[0]["project"], "app")

    def test_without_settings_nothing_counts(self):
        self.assertEqual(friction_journal.type_errors(TSC_OUTPUT, self.app, {}, source="test"), [])

    def run_hook(self, payload) -> subprocess.CompletedProcess:
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run([sys.executable, str(HOOKS / "friction_hook.py")], input=stdin, capture_output=True,
                              text=True, env=self.env, timeout=30)

    def test_the_hook_logs_kit_type_errors_from_bash_output_and_never_speaks(self):
        done = self.run_hook({"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "sess-1",
                              "cwd": str(self.app), "tool_input": {"command": "bunx tsc --noEmit"},
                              "tool_response": {"stdout": TSC_OUTPUT, "stderr": "", "interrupted": False}})
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))
        events = self.events()
        self.assertEqual([(e["kind"], e["rule"], e["session"], e["source"]) for e in events],
                         [("type-error", "TS2322", "sess-1", "mastack-hook"), ("type-error", "TS2724", "sess-1", "mastack-hook")])
        self.assertEqual(list(events[0]), SCHEMA_FIELDS)

    def test_the_hook_passes_on_garbage_other_tools_and_a_disabled_journal(self):
        for payload in ("not json", {"tool_name": "Read", "tool_response": TSC_OUTPUT}):
            done = self.run_hook(payload)
            self.assertEqual((done.returncode, done.stdout), (0, ""))
        self.env["FRICTION_JOURNAL"] = "off"
        self.run_hook({"tool_name": "Bash", "cwd": str(self.app), "tool_response": {"stdout": TSC_OUTPUT}})
        self.assertEqual(self.events(), [])


class RegisterTests(FrictionCase):
    def test_install_adds_the_friction_hook_only_with_friction_settings_and_uninstall_removes_it(self):
        import register
        report: list[str] = []
        ours = {register.command(), register.friction_command()}
        added = register.updated({}, False, ours, report, (), friction=True)
        post = added["hooks"]["PostToolUse"]
        self.assertEqual(post, [{"matcher": "Bash", "hooks": [register.friction_handler()]}])
        self.assertNotIn("PostToolUse", register.updated({}, False, ours, [], (), friction=False).get("hooks", {}))
        kept = {"hooks": {"PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "other"}]}]}}
        again = register.updated(register.updated(kept, False, ours, [], (), friction=True), False, ours, [], (),
                                 friction=True)
        self.assertEqual(len(again["hooks"]["PostToolUse"]), 2, "install is idempotent and keeps other hooks")
        removed = register.updated(again, True, ours, [], (), friction=True)
        self.assertEqual(removed["hooks"]["PostToolUse"], kept["hooks"]["PostToolUse"])
        self.assertTrue(register.friction_wanted(self.config))
        (self.config / "friction.json").unlink()
        self.assertFalse(register.friction_wanted(self.config))


def claude_line(kind: str, content, **extra) -> str:
    return json.dumps({"type": kind, "message": {"role": kind, "content": content}, "timestamp": "2026-11-10T10:00:00.000Z",
                       "cwd": extra.pop("cwd", None), **extra})


class ScanTests(FrictionCase):
    def setUp(self):
        super().setUp()
        self.claude = self.tmp / "claude-projects"
        self.codex = self.tmp / "codex-sessions"
        project = self.claude / "-home-app"
        (project / "s1" / "subagents").mkdir(parents=True)
        (self.codex / "2026" / "11" / "10").mkdir(parents=True)
        self.write_config({"sources": {"claude": str(self.claude), "codex": str(self.codex)}})
        app = str(self.app)
        lines = [
            claude_line("user", "Add a collapsible settings panel", cwd=app),
            claude_line("assistant", [{"type": "text", "text": "I'll add `CollapsibleTrigger` with asChild from UI Kit."},
                                      {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "bunx tsc"}}], cwd=app),
            claude_line("user", [{"type": "tool_result", "tool_use_id": "t1", "content": TSC_OUTPUT}], cwd=app),
            claude_line("assistant", [{"type": "tool_use", "id": "t2", "name": "Edit", "input": {
                "file_path": f"{app}/src/panel.tsx", "old_string": "<CollapsibleTrigger asChild>", "new_string": "<button>"}}], cwd=app),
            claude_line("assistant", [{"type": "text", "text": "The installed `ItemDescription` has no clamp prop, so I override it."}], cwd=app),
            claude_line("user", "No, don't hand-roll the trigger: `CollapsibleTrigger` takes render instead of asChild.", cwd=app),
            claude_line("user", "<command-name>/clear</command-name> don't use CollapsibleTrigger", cwd=app),
            claude_line("user", "Looks good, thanks", cwd=app),
            claude_line("user", "don't touch the README", cwd=app),
            claude_line("assistant", [{"type": "text", "text": "| `CollapsibleTrigger` | has no tests |\n`Button` and the dialog have no measurable case here."}], cwd=app),
            claude_line("user", "Push it now, we can't wait. The `Button` looks fine.", cwd=app),
        ]
        (project / "s1.jsonl").write_text("\n".join(lines) + "\n")
        (project / "s1" / "subagents" / "agent-a.jsonl").write_text(
            claude_line("user", "Don't use `CollapsibleTrigger` asChild, use render instead", cwd=app, isSidechain=True) + "\n")
        codex = [
            {"timestamp": "2026-11-10T11:00:00Z", "type": "session_meta", "payload": {"id": "cx-1", "cwd": app}},
            {"timestamp": "2026-11-10T11:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": "# AGENTS.md instructions\nDon't use CollapsibleTrigger wrong"}]}},
            {"timestamp": "2026-11-10T11:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant",
             "content": [{"type": "output_text", "text": "Using `ItemDescription` from the UI Kit for the subtitle."}]}},
            {"timestamp": "2026-11-10T11:00:03Z", "type": "response_item", "payload": {"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": "Not like that: there is already `ItemBody` for full text."}]}},
        ]
        (self.codex / "2026" / "11" / "10" / "rollout-cx-1.jsonl").write_text("\n".join(json.dumps(c) for c in codex) + "\n")

    def test_scan_flags_corrections_type_errors_reverts_and_admissions_with_reasons_once(self):
        dry = self.run_friction("scan", "--dry-run")
        self.assertEqual(self.events(), [], "a dry run writes nothing")
        self.assertIn("owner-correction", dry.stdout)
        self.run_friction("scan")
        events = self.events()
        summary = sorted((e["kind"], e["component"], e["session"]) for e in events)
        self.assertEqual(summary, sorted([
            ("type-error", "CollapsibleTrigger", "s1"), ("type-error", "Bell", "s1"),
            ("misuse", "CollapsibleTrigger", "s1"), ("misuse", "ItemDescription", "s1"),
            ("owner-correction", "CollapsibleTrigger", "s1"), ("owner-correction", "ItemBody", "cx-1"),
        ]), json.dumps(events, indent=1))
        for item in events:
            self.assertEqual(list(item), SCHEMA_FIELDS)
            self.assertTrue(item["why"], item)
            self.assertEqual(item["source"], "mastack-scan")
            self.assertEqual(item["project"], "app")
        revert = next(e for e in events if e["kind"] == "misuse" and e["component"] == "CollapsibleTrigger")
        self.assertIn("removed CollapsibleTrigger", revert["why"])
        correction = next(e for e in events if e["kind"] == "owner-correction" and e["session"] == "s1")
        self.assertIn("instead", correction["why"])
        self.run_friction("scan")
        self.assertEqual(len(self.events()), len(events), "a second run reads only new lines")

    def test_a_type_error_the_hook_already_logged_is_not_logged_again(self):
        friction_journal.append(friction_journal.type_errors(TSC_OUTPUT, self.app, self.config_data(), session="s1",
                                                             source="mastack-hook"), {"FRICTION_JOURNAL": str(self.journal)})
        self.run_friction("scan")
        self.assertEqual(sum(1 for e in self.events() if e["kind"] == "type-error"), 2)


def git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}).stdout


class VendorTests(FrictionCase):
    def setUp(self):
        super().setUp()
        self.upstream = self.tmp / "upstream"
        kit = self.upstream / "packages" / "kit"
        (kit / "src" / "components").mkdir(parents=True)
        (kit / "package.json").write_text('{"name": "@acme/ui-kit", "version": "1.0.0"}\n')
        (kit / "src" / "components" / "button.tsx").write_text("export const Button = 1;\n")
        (kit / "src" / "components" / "card.tsx").write_text("export const Card = 1;\n")
        git(self.upstream, "init", "-q")
        git(self.upstream, "add", ".")
        git(self.upstream, "commit", "-q", "-m", "kit 1.0.0")
        (kit / "src" / "components" / "card.tsx").write_text("export const Card = 2;\n")
        (kit / "package.json").write_text('{"name": "@acme/ui-kit", "version": "1.1.0"}\n')
        git(self.upstream, "commit", "-q", "-am", "kit 1.1.0")
        self.copy = self.home / "shop" / "packages" / "ui-kit"
        (self.copy / "src" / "components").mkdir(parents=True)
        (self.copy / "dist").mkdir()
        (self.copy / "package.json").write_text('{"name": "@shop/ui-kit", "version": "1.0.0"}\n')
        (self.copy / "src" / "components" / "button.tsx").write_text("export const Button = 1;\nexport const extra = 2;\n")
        (self.copy / "src" / "components" / "card.tsx").write_text("export const Card = 1;\n")
        (self.copy / "src" / "components" / "frame-swap.tsx").write_text("export const FrameSwap = 1;\n")
        (self.copy / "dist" / "index.js").write_text("built\n")
        (self.home / "shop" / ".git").mkdir()
        self.write_config({"vendored": [{"path": str(self.copy), "package": "@acme/ui-kit", "upstream": str(self.upstream),
                                         "upstream_path": "packages/kit"}]})

    def test_vendor_lists_local_patches_against_the_base_version_once(self):
        out = self.run_friction("vendor")
        events = self.events()
        self.assertEqual(sorted((e["kind"], e["component"], e["file"]) for e in events), [
            ("vendored-patch", "Button", "src/components/button.tsx"),
            ("vendored-patch", "FrameSwap", "src/components/frame-swap.tsx")])
        self.assertEqual({e["project"] for e in events}, {"shop"})
        button = next(e for e in events if e["component"] == "Button")
        self.assertIn("kit patched for app need", button["detail"])
        self.assertIn("modified (+1 -0)", button["detail"])
        self.assertIn("1.0.0", button["why"])
        self.assertIn("2 patched files", out.stdout)
        self.run_friction("vendor")
        self.assertEqual(len(self.events()), 2, "an unchanged patch is not logged again")
        (self.copy / "src" / "components" / "card.tsx").write_text("export const Card = 3;\n")
        self.run_friction("vendor")
        self.assertEqual([e["component"] for e in self.events()[2:]], ["Card"])

    def test_scan_runs_vendor_once_a_week(self):
        self.run_friction("scan")
        self.assertEqual(sum(1 for e in self.events() if e["kind"] == "vendored-patch"), 2)
        (self.copy / "src" / "components" / "card.tsx").write_text("export const Card = 3;\n")
        self.run_friction("scan")
        self.assertEqual(sum(1 for e in self.events() if e["kind"] == "vendored-patch"), 2, "not again within the week")


class CommandTests(FrictionCase):
    def test_log_records_a_correction_with_project_and_session(self):
        self.env["CLAUDE_CODE_SESSION_ID"] = "sess-9"
        self.run_friction("log", "--package", "@acme/ui-kit", "--component", "Item", "Item clamps its description;",
                          "full text goes in ItemBody")
        [item] = self.events()
        self.assertEqual((item["kind"], item["project"], item["session"], item["source"], item["component"]),
                         ("owner-correction", "app", "sess-9", "friction-command", "Item"))
        self.assertEqual(item["detail"], "Item clamps its description; full text goes in ItemBody")
        self.assertEqual(self.run_friction("log", check=False).returncode, 2, "a correction needs its text")

    def test_log_guesses_the_package_from_an_alias_or_component(self):
        self.run_friction("log", "use", "`ItemBody`", "for", "full", "text")
        self.assertEqual(self.events()[0]["package"], "@acme/ui-kit")
        self.run_friction("log", "the", "spacing", "is", "wrong")
        self.assertEqual(self.events()[1]["package"], "unknown")

    def test_the_skill_script_logs_through_the_same_command(self):
        script = ROOT / "skills" / "friction" / "scripts" / "log.py"
        proc = subprocess.run([sys.executable, str(script), "--session", "sess-2", "UI Kit Sheet has a body slot"],
                              capture_output=True, text=True, env=self.env, cwd=self.app, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual((self.events()[0]["session"], self.events()[0]["package"]), ("sess-2", "@acme/ui-kit"))

    def test_plist_runs_the_daily_scan_in_the_background(self):
        plist = plistlib.loads(self.run_friction("plist").stdout.encode())
        self.assertEqual(plist["Label"], "com.mastack.friction-scan")
        self.assertEqual(plist["ProgramArguments"][-2:], ["scan", "--quiet"])
        self.assertEqual(plist["StartInterval"], 86400)
        self.assertEqual(plist["ProcessType"], "Background")
        self.assertTrue(plist["RunAtLoad"])


if __name__ == "__main__":
    unittest.main()
