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


class FrictionT3Tests(unittest.TestCase):
    def test_t3_wrapped_user_request_filters_agent_messages_and_deduplicates_on_all(self):
        with tempfile.TemporaryDirectory(prefix="mastack-t3-friction-") as tmp:
            base = pathlib.Path(tmp)
            cfg = base / "config"
            state = base / "state"
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

            env = {**os.environ, "MASTACK_CONFIG": str(cfg), "MASTACK_HOOK_STATE": str(state),
                   "XDG_STATE_HOME": str(state)}
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
                "src/panel.tsx(4,10): error TS2322: Type '{ asChild: true; }' is not assignable "
                "to type 'IntrinsicAttributes & CollapsibleTriggerProps'.\n"
            )
            full_lines = [
                {
                    "step_index": 0, "type": "PLANNER_RESPONSE", "source": "MODEL",
                    "created_at": "2026-11-25T08:00:10Z",
                    "tool_calls": [{"name": "read_file", "args": {"Path": str(app / "src" / "panel.tsx")}}],
                },
                {
                    "step_index": 1, "type": "GENERIC", "source": "MODEL",
                    "created_at": "2026-11-25T08:01:01Z", "content": tsc_out,
                },
                {
                    "step_index": 2, "type": "PLANNER_RESPONSE", "source": "MODEL",
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
                    "step_index": 3, "type": "USER_INPUT", "source": "USER_EXPLICIT",
                    "created_at": "2026-11-25T08:02:00Z",
                    "content": (
                        "<USER_REQUEST>\n<t3_code_instructions>\nLong instructions block\n"
                        "</t3_code_instructions>\nNo, don't hand-roll it: use `CollapsibleTrigger` with render instead.\n"
                        "</USER_REQUEST>"
                    ),
                },
            ]
            (logs_dir / "transcript_full.jsonl").write_text("\n".join(json.dumps(x) for x in full_lines) + "\n")

            env = {
                **os.environ,
                "MASTACK_CONFIG": str(cfg),
                "MASTACK_HOOK_STATE": str(state),
                "XDG_STATE_HOME": str(state),
                "FRICTION_JOURNAL": str(journal),
            }
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
            self.assertEqual(len(turns), 1)
            self.assertEqual((turns[0]["project"], turns[0]["session"]), ("my-app", "conv-agy-42"))
            self.assertIn("CollapsibleTrigger", turns[0]["text"])


if __name__ == "__main__":
    unittest.main()
