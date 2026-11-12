#!/usr/bin/env python3
"""PostToolUse hook for Bash: log TypeScript errors about your packages to the friction journal.

    hooks/friction_hook.py < hook.json

When a Bash call's output holds a TypeScript error (TS2305, TS2322, TS2339, TS2724, ...) whose message names a
module under a scope in `~/.config/mastack/friction.json`, or names a type or component the erroring file imports
from such a package, it appends one `type-error` event per distinct error to the friction journal
(hooks/friction_journal.py), with the session, the project and why it counted. An application's own type errors
are never logged.

It only observes: it prints nothing, never blocks and exits 0, also on unreadable input or a journal it cannot
write. Without friction.json, or with FRICTION_JOURNAL=off, it does nothing. `bin/install` registers it when
friction.json exists.
"""
from __future__ import annotations

import json
import sys

import friction_journal

HOOK_TIMEOUT = 10  # seconds, as bin/install registers it; a run takes milliseconds
MAX_OUTPUT = 2_000_000


def output_of(data: dict) -> str:
    response = data.get("tool_response")
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        return "\n".join(str(response.get(key) or "") for key in ("stdout", "stderr", "output"))
    return ""


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if not isinstance(data, dict) or data.get("tool_name") != "Bash":
            return 0
        text = output_of(data)[-MAX_OUTPUT:]
        if "error TS" not in text:
            return 0
        config = friction_journal.load_config()
        events = friction_journal.type_errors(text, data.get("cwd"), config, session=data.get("session_id"),
                                              source="mastack-hook")
        friction_journal.append(events)
    except Exception:  # an observer never breaks the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
