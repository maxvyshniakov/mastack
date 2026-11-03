#!/usr/bin/env python3
"""macOS shell pitfalls, a Claude Code PreToolUse[Bash] check.

Denies Bash tool commands that keep failing on macOS (BSD tools instead of GNU) and names the form that works.
Add a pattern only after transcripts show it recurring across sessions. Each pattern is matched line by line on
the raw command, quoted text included, at the start of a line or after a separator, space or opening bracket.
"""
from __future__ import annotations

import re
import sys

import hook_io

START = r"(?:^|(?<=[;&|({`\s]))"
BLANK = r"[ \t\r\f\v]+"
PITFALLS = (
    (re.compile(START + "timeout" + BLANK + "[0-9]", re.M),
     "macOS has no GNU `timeout`. Drop it: give the Bash tool its timeout parameter, or run long commands with "
     "run_in_background."),
    (re.compile(START + "cat" + BLANK + "-[a-zA-Z]*A", re.M),
     "BSD cat has no -A. Use `cat -vet` to show tabs, line ends and control characters."),
)


def check(data: dict):
    command = hook_io.command_of(data)
    if not command:
        return None
    for pattern, message in PITFALLS:
        if pattern.search(command):
            return hook_io.deny(message)
    return None


if __name__ == "__main__":
    sys.exit(hook_io.run("shell-pitfalls", check))
