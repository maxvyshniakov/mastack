#!/usr/bin/env python3
"""Every Bash check in one process: the hook `bin/install` registers for PreToolUse[Bash].

One process instead of one per check saves the interpreter start of each. A check is imported only when the
command holds the text it looks for, so `ls` pays for none of the parsers. A deny from any check wins and names
every check that denied; otherwise an ask (the lease guard's owner override) is passed on. A check that fails is
logged to guard.log and skipped, so one broken check never blocks a command or silences the others.

The checks that only parse run first. The lease guard, which asks slotfather and ps about each pid, runs last and
only when nothing is denied yet (a deny already wins). All of it shares a BUDGET shorter than the hook's timeout:
each subprocess gets what is left of it, and once it is spent the hook answers with what it has, so a slow
slotfather never lets Claude Code's timeout drop a deny that was already found.

After the checks, a command that is not denied goes to the lifecycle observers that wait for its text (hooks/
lifecycle.py), which only watch.

Each check is a module of its own with `check(data) -> (decision, reason) | None`, and runs alone as a hook too:
`python3 hooks/git_guard.py < input.json`.
"""
from __future__ import annotations

import importlib
import sys

import hook_io

HOOK_TIMEOUT = 10  # seconds, as bin/install registers the hook
BUDGET = 7.0       # seconds the checks may spend; the rest is the interpreter's start and a margin

# (module, log name, texts of which the command must contain one for the check to look at it; () for every command)
CHECKS = (
    ("shell_pitfalls", "shell-pitfalls", ()),
    ("git_guard", "git-guard", ("git",)),
    ("zsh_word_split", "zsh-word-split", ("$",)),
    ("unguarded_sequence", "unguarded-sequence", (";", "\n")),
    ("pgrep_self_match", "pgrep-self-match", ("pgrep", "pkill")),
    ("lease_guard", "lease-guard", ("kill",)),
)
ONLY_WITHOUT_DENY = {"lease_guard"}


def triggered(command: str, needles: tuple[str, ...]) -> bool:
    return not needles or any(needle in command for needle in needles)


def decide(data: dict, budget: float = BUDGET):
    command = hook_io.command_of(data)
    if command is None:
        return None
    hook_io.set_budget(budget)
    denies, asks = [], []
    for module, name, needles in CHECKS:
        if not triggered(command, needles) or (denies and module in ONLY_WITHOUT_DENY):
            continue
        if (hook_io.remaining() or 0) <= 0:
            hook_io.log("guard.log", f"bash-guard budget spent before {name}")
            break
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


def guard(data: dict):
    """The hook: the checks' decision, then, for a command that is not denied, the lifecycle observers that wait for
    its text (`lifecycle.PreToolUse` in the machine settings; hooks/lifecycle.py). They see the call and cannot
    change the decision."""
    decision = decide(data)
    try:
        lifecycle = hook_io.config().get("lifecycle")
        if not (decision and decision[0] == "deny") and isinstance(lifecycle, dict) and lifecycle.get("PreToolUse"):
            importlib.import_module("lifecycle").observe(data, hook_io.remaining())
    except Exception as error:  # noqa: BLE001 - an observer never costs the decision
        hook_io.log("guard.log", f"lifecycle observer error {error!r}")
    return decision


if __name__ == "__main__":
    sys.exit(hook_io.run("bash-guard", guard))
