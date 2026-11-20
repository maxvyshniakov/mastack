#!/usr/bin/env python3
"""PostToolUse hook for Bash: log package TypeScript errors and oversized Bash outputs to the friction journal.

    hooks/friction_hook.py < hook.json

When a Bash call's output holds a TypeScript error (TS2305, TS2322, TS2339, TS2724, ...) whose message names a
module under a scope in `~/.config/mastack/friction.json`, or names a type or component the erroring file imports
from such a package, it appends one `type-error` event per distinct error to the friction journal
(hooks/friction_journal.py), with the session, the project and why it counted. An application's own type errors
are never logged.

When a Bash call's output exceeds 8,000 characters (`friction_journal.LARGE_OUTPUT_THRESHOLD`), it also appends a
`note` event (`rule="large-bash-output"`) naming the command so the worst offenders show up by name.

It only observes: it prints nothing, never blocks and exits 0, also on unreadable input or a journal it cannot
write. With FRICTION_JOURNAL=off it does nothing. `bin/install` registers it for Bash.
"""
from __future__ import annotations

import json
import sys

import friction_journal

HOOK_TIMEOUT = 10  # seconds, as bin/install registers it; a run takes milliseconds
MAX_OUTPUT = 2_000_000


def output_of(data: dict) -> tuple[str, int]:
    response = data.get("tool_response")
    if isinstance(response, str):
        return response, len(response)
    if isinstance(response, dict):
        parts = [str(response[key]) for key in ("stdout", "stderr") if response.get(key)]
        if not parts and response.get("output"):
            parts = [str(response["output"])]
        return "\n".join(parts), sum(len(part) for part in parts)
    return "", 0


def main() -> int:
    try:
        if not friction_journal.journal_path():
            return 0
        data = json.loads(sys.stdin.read() or "{}")
        if not isinstance(data, dict) or data.get("tool_name") != "Bash":
            return 0
        raw, raw_size = output_of(data)
        events = []
        tool_input = data.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        large = friction_journal.large_bash_output(raw, command, data.get("cwd"), session=data.get("session_id"),
                                                   source="mastack-hook", size=raw_size)
        if large:
            events.append(large)
        text = raw[-MAX_OUTPUT:]
        if "error TS" in text:
            config = friction_journal.load_config()
            events.extend(friction_journal.type_errors(text, data.get("cwd"), config, session=data.get("session_id"),
                                                       source="mastack-hook"))
        if events:
            friction_journal.append(events)
    except Exception:  # an observer never breaks the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
