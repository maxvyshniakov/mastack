#!/usr/bin/env python3
"""Tests for T3/Antigravity transcript scanning and owner-turns.jsonl indexing in bin/friction."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _t3_env(cfg: pathlib.Path, state: pathlib.Path, journal: pathlib.Path) -> dict[str, str]:
    env = {
        k: v for k, v in os.environ.items()
        if not k.startswith(("MASTACK_", "FRICTION_", "CLAUDE_CODE_SESSION", "CODEX_")) and k != "XDG_STATE_HOME"
    }
    env.update(
        MASTACK_CONFIG=str(cfg),
        MASTACK_HOOK_STATE=str(state),
        MASTACK_FRICTION_STATE=str(state / "mastack" / "friction-scan.json"),
        XDG_STATE_HOME=str(state),
        FRICTION_JOURNAL=str(journal),
    )
    return env


class FrictionT3Tests(unittest.TestCase):
    def test_t3_wrapped_user_request_filters_agent_messages_and_deduplicates_on_all(self):
        with tempfile.TemporaryDirectory(prefix="mastack-t3-friction-") as tmp:
            base = pathlib.Path(tmp)
            cfg = base / "config"
            state = base / "state"
            journal = base / "journal" / "events.jsonl"
            t3_dir = base / "t3" / "antigravity" / "brain" / "conv-123" / ".system_generated" / "logs"
            cfg.mkdir()
            t3_dir.mkdir(parents=True)
            (cfg / "friction.json").write_text(json.dumps({
                "scopes": ["@acme/"],
                "packages": {"@acme/ui": {"aliases": ["UI Kit"]}},
                "sources": {
                    "claude": str(base / "empty-claude"),
                    "codex": str(base / "empty-codex"),
                    "t3": str(base / "t3"),
                },
            }))
            transcript = t3_dir / "transcript.jsonl"
            transcript.write_text("\n".join([
                json.dumps({"type": "PLANNER_RESPONSE", "created_at": "2026-11-24T10:00:00Z",
                            "content": "Using UI Kit Button here."}),
                json.dumps({"type": "USER_INPUT", "source": "USER_EXPLICIT", "created_at": "2026-11-24T10:01:00Z",
                            "content": "<USER_REQUEST>\n<user_request>\nNo, don't use UI Kit Button with custom styles.\n</user_request>\n</USER_REQUEST>\n<ADDITIONAL_METADATA>x</ADDITIONAL_METADATA>"}),
                json.dumps({"type": "USER_INPUT", "source": "USER_EXPLICIT", "created_at": "2026-11-24T10:02:00Z",
                            "content": "<USER_REQUEST>\n[T3 Code: the agent in T3 thread abc sent this message, not the user.]\n</USER_REQUEST>"}),
            ]) + "\n")

            env = _t3_env(cfg, state, journal)
            for flag in ([], ["--all"]):
                proc = subprocess.run([sys.executable, str(ROOT / "bin/friction"), "scan", *flag],
                                      env=env, capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            turns_file = state / "owner-turns.jsonl"
            self.assertTrue(turns_file.is_file())
            rows = [json.loads(line) for line in turns_file.read_text().splitlines() if line]
            self.assertEqual(len(rows), 1, "agent message filtered and --all deduplicated")
            self.assertIn("UI Kit Button", rows[0]["text"])

    def test_antigravity_acp_brain_transcript_discovery_full_fallback_and_detectors(self):
        with tempfile.TemporaryDirectory(prefix="mastack-t3-agy-") as tmp:
            base = pathlib.Path(tmp)
            cfg = base / "config"
            state = base / "state"
            journal = base / "journal" / "events.jsonl"
            app = base / "repos" / "my-app"
            (app / ".git").mkdir(parents=True)
            (app / "src").mkdir()
            (app / "src" / "panel.tsx").write_text(
                'import { CollapsibleTrigger } from "@acme/ui";\n'
            )
            skill_file = base / "home" / ".gemini" / "config" / "skills" / "tdd" / "SKILL.md"
            skill_file.parent.mkdir(parents=True)
            skill_file.write_text("# tdd\n")
            (base / "kit.d.ts").write_text(
                'export { CollapsibleTrigger, Button } from "./ui.js";\n'
            )
            logs_dir = (
                base / "t3" / "antigravity" / "profile-hash-01" / "antigravity-acp"
                / "brain" / "conv-agy-42" / ".system_generated" / "logs"
            )
            cfg.mkdir()
            logs_dir.mkdir(parents=True)
            (cfg / "friction.json").write_text(json.dumps({
                "scopes": ["@acme/"],
                "packages": {"@acme/ui": {"aliases": ["UI Kit"], "types": [str(base / "kit.d.ts")]}},
                "sources": {
                    "claude": str(base / "empty-claude"),
                    "codex": str(base / "empty-codex"),
                    "t3": str(base / "t3"),
                },
            }))

            # Compact transcript.jsonl truncates USER_INPUT inside <t3_code_instructions>
            # (matching real Antigravity behavior); transcript_full.jsonl has the complete lines.
            (logs_dir / "transcript.jsonl").write_text(json.dumps({
                "step_index": 0, "type": "USER_INPUT", "source": "USER_EXPLICIT",
                "created_at": "2026-11-25T08:00:00Z", "truncated_fields": ["content"],
                "content": "<USER_REQUEST>\n<t3_code_instructions>\nTruncated instructions...",
            }) + "\n")

            tsc_out = (
                "Created At: 2026-11-25T08:01:00Z\nCompleted At: 2026-11-25T08:01:01Z\n"
                "Command exited with code 2.\n\nCommand output:\n"
                "src/panel.tsx(4,10): error TS2322: Type '{ asChild: true; }' is not assignable "
                "to type 'IntrinsicAttributes & CollapsibleTriggerProps'.\n"
            )
            # Step 0 is USER_INPUT before any tool call, followed by a read_file on ~/.gemini/skills/tdd/SKILL.md,
            # then a run_command tsc error, then edit_file in my-app: pre-pass must resolve project to my-app.
            full_lines = [
                {
                    "step_index": 0, "type": "USER_INPUT", "source": "USER_EXPLICIT",
                    "created_at": "2026-11-25T08:00:00Z",
                    "content": "<USER_REQUEST>\nAdd a collapsible panel\n</USER_REQUEST>",
                },
                {
                    "step_index": 1, "type": "PLANNER_RESPONSE", "source": "MODEL",
                    "created_at": "2026-11-25T08:00:05Z",
                    "tool_calls": [{"name": "read_file", "args": {"Path": str(skill_file)}}],
                },
                {
                    "step_index": 2, "type": "GENERIC", "source": "MODEL",
                    "created_at": "2026-11-25T08:00:06Z",
                    "content": "Showing lines 1-1 of 1\n1: # tdd\nsrc/panel.tsx(4,10): error TS2322: quoted CollapsibleTriggerProps\n",
                },
                {
                    "step_index": 3, "type": "PLANNER_RESPONSE", "source": "MODEL",
                    "created_at": "2026-11-25T08:00:55Z",
                    "tool_calls": [{"name": "run_command", "args": {"CommandLine": "bunx tsc --noEmit"}}],
                },
                {
                    "step_index": 4, "type": "GENERIC", "source": "MODEL",
                    "created_at": "2026-11-25T08:01:01Z", "content": tsc_out,
                },
                {
                    "step_index": 5, "type": "PLANNER_RESPONSE", "source": "MODEL",
                    "created_at": "2026-11-25T08:01:10Z",
                    "tool_calls": [{
                        "name": "edit_file",
                        "args": {
                            "Path": str(app / "src" / "panel.tsx"),
                            "Target": "<CollapsibleTrigger asChild>",
                            "Replacement": "<button>",
                        },
                    }],
                },
                {
                    "step_index": 6, "type": "USER_INPUT", "source": "USER_EXPLICIT",
                    "created_at": "2026-11-25T08:02:00Z",
                    "content": (
                        "<USER_REQUEST>\n<t3_code_instructions>\nLong instructions block\n"
                        "</t3_code_instructions>\nNo, don't hand-roll it: use `CollapsibleTrigger` with render instead.\n"
                        "</USER_REQUEST>"
                    ),
                },
            ]
            (logs_dir / "transcript_full.jsonl").write_text("\n".join(json.dumps(x) for x in full_lines) + "\n")

            env = _t3_env(cfg, state, journal)
            proc = subprocess.run([sys.executable, str(ROOT / "bin/friction"), "scan"],
                                  env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            events = [json.loads(line) for line in journal.read_text().splitlines() if line]
            summary = sorted((e["kind"], e["component"], e["project"], e["session"]) for e in events)
            self.assertEqual(summary, sorted([
                ("type-error", "CollapsibleTrigger", "my-app", "conv-agy-42"),
                ("misuse", "CollapsibleTrigger", "my-app", "conv-agy-42"),
                ("owner-correction", "CollapsibleTrigger", "my-app", "conv-agy-42"),
            ]), json.dumps(events, indent=1))

            turns = [json.loads(line) for line in (state / "owner-turns.jsonl").read_text().splitlines() if line]
            self.assertEqual(len(turns), 2)
            self.assertEqual({t["project"] for t in turns}, {"my-app"})
            self.assertEqual({t["session"] for t in turns}, {"conv-agy-42"})

    def test_compact_only_stringified_tool_args_and_non_command_generic_ignored(self):
        with tempfile.TemporaryDirectory(prefix="mastack-t3-compact-") as tmp:
            base = pathlib.Path(tmp)
            cfg = base / "config"
            state = base / "state"
            journal = base / "journal" / "events.jsonl"
            app = base / "repos" / "compact-app"
            (app / ".git").mkdir(parents=True)
            (app / "src").mkdir()
            (app / "src" / "panel.tsx").write_text('import { CollapsibleTrigger } from "@acme/ui";\n')
            (base / "kit.d.ts").write_text('export { CollapsibleTrigger } from "./ui.js";\n')
            logs_dir = (
                base / "t3" / "antigravity" / "hash-02" / "antigravity-acp"
                / "brain" / "conv-compact-9" / ".system_generated" / "logs"
            )
            cfg.mkdir()
            logs_dir.mkdir(parents=True)
            (cfg / "friction.json").write_text(json.dumps({
                "scopes": ["@acme/"],
                "packages": {"@acme/ui": {"aliases": ["UI Kit"], "types": [str(base / "kit.d.ts")]}},
                "sources": {
                    "claude": str(base / "empty-claude"),
                    "codex": str(base / "empty-codex"),
                    "t3": str(base / "t3"),
                },
            }))

            # Only transcript.jsonl exists (no transcript_full.jsonl), with JSON-stringified arg values.
            panel_path = str(app / "src" / "panel.tsx")
            compact_lines = [
                {
                    "step_index": 0, "type": "PLANNER_RESPONSE", "source": "MODEL",
                    "created_at": "2026-11-25T09:00:00Z",
                    "tool_calls": [{"name": "read_file", "args": {"Path": json.dumps(panel_path)}}],
                },
                {
                    # Non-command GENERIC quoting a TS error (e.g. from read_file / t3_thread_read) must be ignored.
                    "step_index": 1, "type": "GENERIC", "source": "MODEL",
                    "created_at": "2026-11-25T09:00:01Z",
                    "content": "Showing lines 1-3 of 3\nsrc/panel.tsx(4,10): error TS2322: Type 'x' not assignable to 'CollapsibleTriggerProps'.\n",
                },
                {
                    "step_index": 2, "type": "PLANNER_RESPONSE", "source": "MODEL",
                    "created_at": "2026-11-25T09:00:05Z",
                    "tool_calls": [{"name": "run_command", "args": {"CommandLine": json.dumps("bunx tsc")}}],
                },
                {
                    "step_index": 3, "type": "GENERIC", "source": "MODEL",
                    "created_at": "2026-11-25T09:00:06Z",
                    "content": "Command exited with code 2.\n\nCommand output:\nsrc/panel.tsx(4,10): error TS2322: Type 'x' not assignable to 'CollapsibleTriggerProps'.\n",
                },
                {
                    "step_index": 4, "type": "PLANNER_RESPONSE", "source": "MODEL",
                    "created_at": "2026-11-25T09:00:10Z",
                    "tool_calls": [{
                        "name": "edit_file",
                        "args": {
                            "Path": json.dumps(panel_path),
                            "Target": json.dumps("<CollapsibleTrigger asChild>"),
                            "Replacement": json.dumps("<button>"),
                        },
                    }],
                },
            ]
            (logs_dir / "transcript.jsonl").write_text("\n".join(json.dumps(x) for x in compact_lines) + "\n")

            env = _t3_env(cfg, state, journal)
            proc = subprocess.run([sys.executable, str(ROOT / "bin/friction"), "scan"],
                                  env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            events = [json.loads(line) for line in journal.read_text().splitlines() if line]
            summary = sorted((e["kind"], e["component"], e["project"], e["session"]) for e in events)
            self.assertEqual(summary, sorted([
                ("type-error", "CollapsibleTrigger", "compact-app", "conv-compact-9"),
                ("misuse", "CollapsibleTrigger", "compact-app", "conv-compact-9"),
            ]), json.dumps(events, indent=1))

    def test_t3_batched_planner_response_pairs_large_run_command_output_and_ignores_read_file(self):
        with tempfile.TemporaryDirectory(prefix="mastack-t3-large-") as tmp:
            base = pathlib.Path(tmp)
            cfg = base / "config"
            state = base / "state"
            journal = base / "journal" / "events.jsonl"
            app = base / "repos" / "batch-app"
            (app / ".git").mkdir(parents=True)
            (app / "src").mkdir()
            panel = app / "src" / "panel.tsx"
            panel.write_text("export const x = 1;\n")
            logs_dir = (
                base / "t3" / "antigravity" / "hash-03" / "antigravity-acp"
                / "brain" / "conv-batch-7" / ".system_generated" / "logs"
            )
            cfg.mkdir()
            logs_dir.mkdir(parents=True)
            (cfg / "friction.json").write_text(json.dumps({
                "sources": {
                    "claude": str(base / "empty-claude"),
                    "codex": str(base / "empty-codex"),
                    "t3": str(base / "t3"),
                },
            }))

            big_file = "Showing lines 1-500 of 500\n" + ("a" * 9_000)
            big_diff = "Created At: 2026-11-28T10:00:01Z\nCommand exited with code 0.\n\nCommand output:\n" + ("d" * 8_500)
            big_verify = "Created At: 2026-11-28T10:00:02Z\nCommand exited with code 0.\n\nCommand output:\n" + ("v" * 9_000)
            lines = [
                {
                    "step_index": 0, "type": "USER_INPUT", "source": "USER_EXPLICIT",
                    "created_at": "2026-11-28T10:00:00Z",
                    "content": "<USER_REQUEST>\nCheck the diff and run verify\n</USER_REQUEST>",
                },
                {
                    "step_index": 1, "type": "PLANNER_RESPONSE", "source": "MODEL",
                    "created_at": "2026-11-28T10:00:01Z",
                    "tool_calls": [
                        {"name": "read_file", "args": {"Path": json.dumps(str(panel))}},
                        {"name": "run_command", "args": {"CommandLine": json.dumps("git diff HEAD~1")}},
                        {"name": "run_command", "args": {"CommandLine": json.dumps("bun run verify")}},
                    ],
                },
                {"step_index": 2, "type": "GENERIC", "source": "MODEL",
                 "created_at": "2026-11-28T10:00:02Z", "content": big_file},
                {"step_index": 3, "type": "GENERIC", "source": "MODEL",
                 "created_at": "2026-11-28T10:00:03Z", "content": big_diff},
                {"step_index": 4, "type": "GENERIC", "source": "MODEL",
                 "created_at": "2026-11-28T10:00:04Z", "content": big_verify},
            ]
            (logs_dir / "transcript.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")

            env = _t3_env(cfg, state, journal)
            proc = subprocess.run([sys.executable, str(ROOT / "bin/friction"), "scan"],
                                  env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("warning: no packages", proc.stderr)

            events = [json.loads(line) for line in journal.read_text().splitlines() if line]
            self.assertEqual(
                [(e["kind"], e["package"], e["rule"], e["component"], e["project"], e["session"], e["source"])
                 for e in events],
                [
                    ("note", "mastack", "large-bash-output", "git/diff", "batch-app", "conv-batch-7", "mastack-scan"),
                    ("note", "mastack", "large-bash-output", "bun/run", "batch-app", "conv-batch-7", "mastack-scan"),
                ],
                json.dumps(events, indent=1),
            )
            turns = [json.loads(line) for line in (state / "owner-turns.jsonl").read_text().splitlines() if line]
            self.assertEqual(len(turns), 1)
            self.assertEqual(turns[0]["project"], "batch-app")


if __name__ == "__main__":
    unittest.main()
