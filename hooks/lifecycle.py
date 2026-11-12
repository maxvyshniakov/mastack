#!/usr/bin/env python3
"""Lifecycle hooks: tell other tools when an agent's subagent or session stops, and which agent runs a command.

    hooks/lifecycle.py EVENT < hook.json

`bin/install` registers this for each Claude Code event the machine settings list under `lifecycle`
(`~/.config/mastack/hooks.json`), and `bash_guard.py` runs the `PreToolUse` observers of Bash calls itself, so they
cost no process of their own:

    "lifecycle": {
      "SubagentStop": ["~/.local/bin/junkfather hook"],
      "SessionEnd":   ["~/.local/bin/junkfather hook"],
      "Stop":         ["~/.local/bin/junkfather hook"],
      "PreToolUse":   [{"command": "~/.local/bin/junkfather hook", "contains": ["junkfather"]}]
    }

An entry is a shell command, or {"command", "contains"}: then it runs only when the event's text (for a Bash call,
its command) holds one of those strings. Each command gets the event's JSON on stdin and runs through /bin/sh; its
output is discarded and all of them share BUDGET seconds. A lifecycle hook only observes: it never blocks a stop or
a tool call, prints nothing and exits 0, also when a command fails, hangs or is missing (logged to guard.log).
Claude Code's `Stop` ends a main-agent turn, not the session; `SessionEnd` ends the session.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

import hook_io

EVENTS = ("SubagentStart", "SubagentStop", "Stop", "SessionStart", "SessionEnd")  # what bin/install registers
HOOK_TIMEOUT = 30  # seconds, as bin/install registers the hook
BUDGET = 20.0
OBSERVER_BUDGET = 2.0  # seconds the PreToolUse observers may add to a Bash call


def entries(event: str) -> list[tuple[str, list[str]]]:
    """(command, texts it waits for; [] for always) of this event, from the machine settings."""
    lifecycle = hook_io.config().get("lifecycle")
    listed = lifecycle.get(event) if isinstance(lifecycle, dict) else None
    found = []
    for entry in listed if isinstance(listed, list) else []:
        if isinstance(entry, str) and entry.strip():
            found.append((entry, []))
        elif isinstance(entry, dict) and isinstance(entry.get("command"), str) and entry["command"].strip():
            found.append((entry["command"], hook_io.strings(entry.get("contains"))))
    return found


def run(event: str, data: dict, raw: str, budget: float) -> int:
    """Run the event's commands that apply; returns how many ran."""
    text = hook_io.command_of(data) if event == "PreToolUse" else raw
    deadline = time.monotonic() + budget
    ran = 0
    for command, needles in entries(event):
        if needles and not (text and any(needle in text for needle in needles)):
            continue
        left = deadline - time.monotonic()
        if left <= 0.05:
            hook_io.log("guard.log", f"lifecycle {event} budget spent before {command!r}")
            break
        try:
            result = subprocess.run(["/bin/sh", "-c", command], input=raw, text=True, timeout=left,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if result.returncode:
                hook_io.log("guard.log", f"lifecycle {event} {command!r} exited {result.returncode}: "
                                         f"{result.stderr.strip()[:200]}")
        except (OSError, subprocess.TimeoutExpired) as error:
            hook_io.log("guard.log", f"lifecycle {event} {command!r} failed: {error!r}")
        ran += 1
    return ran


def observe(data: dict) -> None:
    """bash_guard's call for a Bash command that is not denied: the PreToolUse observers."""
    try:
        if entries("PreToolUse"):
            run("PreToolUse", data, json.dumps(data), OBSERVER_BUDGET)
    except Exception as error:  # noqa: BLE001 - an observer never changes the decision
        hook_io.log("guard.log", f"lifecycle PreToolUse error {error!r}")


def main(argv: list[str]) -> int:
    event = argv[1] if len(argv) > 1 else ""
    try:
        raw = sys.stdin.read()
        try:
            data = json.loads(raw)
        except ValueError:
            data = {}
        if isinstance(data, dict) and data.get("hook_event_name") not in (None, event):
            hook_io.log("guard.log", f"lifecycle {event} got {data.get('hook_event_name')}")
        run(event, data if isinstance(data, dict) else {}, raw, BUDGET)
    except Exception as error:  # noqa: BLE001 - fail open
        hook_io.log("guard.log", f"lifecycle {event} error {error!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
