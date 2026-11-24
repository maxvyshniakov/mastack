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


if __name__ == "__main__":
    unittest.main()
