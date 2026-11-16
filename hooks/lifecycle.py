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

A `PreToolUse` entry may also say:

    "background": true    only for a Bash call with `run_in_background: true`
    "rewrite": true       a rewriter: its stdout is a PreToolUse answer, {"hookSpecificOutput": {"updatedInput":
                          {...}}}, the call's whole input with its `command` rewritten; bash_guard.py passes the first
                          such answer to Claude Code (hook_io.Answer), without a permission decision of its own, so
                          Claude Code's rules judge the rewritten call. No answer, a failure or a timeout leaves the
                          call as it was. Rewriters run before the observers, within REWRITE_BUDGET seconds.
    "allow": [rules]      permission rules bin/install adds to Claude Code's `permissions.allow` while the entry is
                          listed (hooks/register.py), such as the one that lets a rewriter's added line run

    "PreToolUse": [{"command": "~/.local/bin/junkfather hook", "background": true, "rewrite": true,
                    "allow": ["Bash(<its absolute path> background:*)"]}]
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import NamedTuple

import hook_io

EVENTS = ("SubagentStart", "SubagentStop", "Stop", "SessionStart", "SessionEnd")  # what bin/install registers
HOOK_TIMEOUT = 30  # seconds, as bin/install registers the hook
BUDGET = 20.0
OBSERVER_BUDGET = 2.0  # seconds the PreToolUse observers may add to a Bash call
REWRITE_BUDGET = 3.0  # seconds the PreToolUse rewriters may add to a Bash call


class Entry(NamedTuple):
    command: str
    contains: list  # texts of which the event's text must hold one; [] for always
    background: bool = False  # PreToolUse: only a Bash call with run_in_background
    rewrite: bool = False  # PreToolUse: a rewriter
    allow: tuple = ()  # permission rules bin/install registers for it


def entries(event: str, config: dict | None = None) -> list[Entry]:
    """The entries of this event, from the machine settings (`config`, default hook_io.config())."""
    lifecycle = (hook_io.config() if config is None else config).get("lifecycle")
    listed = lifecycle.get(event) if isinstance(lifecycle, dict) else None
    found = []
    for entry in listed if isinstance(listed, list) else []:
        if isinstance(entry, str) and entry.strip():
            found.append(Entry(entry, []))
        elif isinstance(entry, dict) and isinstance(entry.get("command"), str) and entry["command"].strip():
            found.append(Entry(entry["command"], hook_io.strings(entry.get("contains")),
                               entry.get("background") is True, entry.get("rewrite") is True,
                               tuple(hook_io.strings(entry.get("allow")))))
    return found


def applies(entry: Entry, data: dict, text: str | None) -> bool:
    if entry.contains and not (text and any(needle in text for needle in entry.contains)):
        return False
    tool_input = data.get("tool_input")
    return not entry.background or (isinstance(tool_input, dict) and tool_input.get("run_in_background") is True)


def run(event: str, data: dict, raw: str, budget: float) -> int:
    """Run the event's commands that apply (for PreToolUse its observers, not its rewriters); returns how many ran."""
    text = hook_io.command_of(data) if event == "PreToolUse" else raw
    deadline = time.monotonic() + budget
    ran = 0
    for entry in entries(event):
        command = entry.command
        if entry.rewrite or not applies(entry, data, text):
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


def rewrite(data: dict, left: float | None = None) -> dict | None:
    """bash_guard's call for a Bash command that is not denied: the first rewriter's `updatedInput`, within
    REWRITE_BUDGET and what is `left` of the checks' budget; None when none answers."""
    try:
        budget = REWRITE_BUDGET if left is None else min(REWRITE_BUDGET, left)
        deadline = time.monotonic() + budget
        text, raw = hook_io.command_of(data), json.dumps(data)
        for entry in entries("PreToolUse"):
            if not entry.rewrite or not applies(entry, data, text):
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0.1:
                hook_io.log("guard.log", f"lifecycle rewrite budget spent before {entry.command!r}")
                return None
            try:
                result = subprocess.run(["/bin/sh", "-c", entry.command], input=raw, text=True, timeout=remaining,
                                        capture_output=True)
            except (OSError, subprocess.TimeoutExpired) as error:
                hook_io.log("guard.log", f"lifecycle rewrite {entry.command!r} failed: {error!r}")
                continue
            if result.returncode:
                hook_io.log("guard.log", f"lifecycle rewrite {entry.command!r} exited {result.returncode}: "
                                         f"{result.stderr.strip()[:200]}")
                continue
            updated = updated_input(result.stdout)
            if updated is not None:
                return updated
    except Exception as error:  # noqa: BLE001 - a rewriter never changes the decision
        hook_io.log("guard.log", f"lifecycle rewrite error {error!r}")
    return None


def updated_input(stdout: str) -> dict | None:
    """The `updatedInput` of a rewriter's answer: an object whose `command` is text; None for no answer."""
    if not stdout.strip():
        return None
    try:
        answer = json.loads(stdout)
    except ValueError:
        hook_io.log("guard.log", "lifecycle rewrite answered with something that is not JSON")
        return None
    output = answer.get("hookSpecificOutput") if isinstance(answer, dict) else None
    updated = output.get("updatedInput") if isinstance(output, dict) else None
    if isinstance(updated, dict) and isinstance(updated.get("command"), str):
        return updated
    hook_io.log("guard.log", "lifecycle rewrite answered without an updatedInput holding a command")
    return None


def observe(data: dict, left: float | None = None) -> None:
    """bash_guard's call for a Bash command that is not denied: the PreToolUse observers, within OBSERVER_BUDGET and
    what is `left` of the checks' budget, so the decision always reaches Claude Code before the hook's timeout."""
    try:
        budget = OBSERVER_BUDGET if left is None else min(OBSERVER_BUDGET, left)
        if budget <= 0.1:
            hook_io.log("guard.log", "lifecycle PreToolUse skipped: the checks spent the budget")
        elif any(not entry.rewrite for entry in entries("PreToolUse")):
            run("PreToolUse", data, json.dumps(data), budget)
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
