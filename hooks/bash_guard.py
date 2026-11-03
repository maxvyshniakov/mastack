#!/usr/bin/env python3
"""Every Bash check in one process: the hook `bin/install` registers for PreToolUse[Bash].

One process instead of one per check saves the interpreter start of each. A check is imported only when the
command holds the text it looks for, so `ls` pays for none of the parsers. A deny from any check wins and names
every check that denied; otherwise an ask (the lease guard's owner override) is passed on. A check that fails is
logged to guard.log and skipped, so one broken check never blocks a command or silences the others.

Each check is a module of its own with `check(data) -> (decision, reason) | None`, and runs alone as a hook too:
`python3 hooks/git_guard.py < input.json`.
"""
from __future__ import annotations

import importlib
import sys

import hook_io

# (module, log name, texts of which the command must contain one for the check to look at it; () for every command)
CHECKS = (
    ("shell_pitfalls", "shell-pitfalls", ()),
    ("git_guard", "git-guard", ("git",)),
    ("zsh_word_split", "zsh-word-split", ("$",)),
    ("unguarded_sequence", "unguarded-sequence", (";", "\n")),
    ("lease_guard", "lease-guard", ("kill",)),
    ("pgrep_self_match", "pgrep-self-match", ("pgrep", "pkill")),
)


def triggered(command: str, needles: tuple[str, ...]) -> bool:
    return not needles or any(needle in command for needle in needles)


def decide(data: dict):
    command = hook_io.command_of(data)
    if command is None:
        return None
    denies, asks = [], []
    for module, name, needles in CHECKS:
        if not triggered(command, needles):
            continue
        try:
            decision = importlib.import_module(module).check(data)
        except Exception as error:  # noqa: BLE001 - fail open, check by check
            hook_io.log("guard.log", f"{name} error {error!r}")
            continue
        if decision:
            (denies if decision[0] == "deny" else asks).append(decision[1])
    if denies:
        return hook_io.deny("\n\n".join(denies))
    if asks:
        return hook_io.ask("\n\n".join(asks))
    return None


if __name__ == "__main__":
    sys.exit(hook_io.run("bash-guard", decide))
