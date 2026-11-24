#!/usr/bin/env python3
"""Every Bash check in one process: the hook `bin/install` registers for PreToolUse[Bash].

One process instead of one per check saves the interpreter start of each. A check is imported only when the
command holds the text it looks for, so `ls` pays for none of the parsers (neither `shell` nor a check's own). A deny
from any check wins and names
every check that denied; otherwise an ask (the lease guard's owner override) is passed on. A check that fails is
logged to guard.log and skipped, so one broken check never blocks a command or silences the others; the release
guard is the exception (FAIL_CLOSED): a command it is triggered for is refused when it fails or has no time left,
because a skipped release check would let a publication through. It runs first, before the checks that ask other
processes, so their time does not starve it.

The checks that only parse run first. The lease guard, which asks slotfather and ps about each pid, runs last and
only when nothing is denied yet (a deny already wins). All of it shares a BUDGET shorter than the hook's timeout:
each subprocess gets what is left of it, and once it is spent the hook answers with what it has, so a slow
slotfather never lets Claude Code's timeout drop a deny that was already found.

After the checks, a command that is not denied goes to the lifecycle rewriters, the first of which may answer with
the call's input rewritten, and to the observers that wait for its text (hooks/lifecycle.py), which only watch.

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
    ("release_guard", "release-guard", ("publish", "release", "promote", "push", "access", "visibility",
                                     "--public", "private=", "pages", "workflow")),
    ("shell_pitfalls", "shell-pitfalls", ()),
    ("git_guard", "git-guard", ("git",)),
    ("zsh_word_split", "zsh-word-split", ("$",)),
    ("unguarded_sequence", "unguarded-sequence", (";", "\n")),
    ("pgrep_self_match", "pgrep-self-match", ("pgrep", "pkill")),
    ("slot_label", "slot-label", ("slotfather",)),
    ("codex_credits", "codex-credits", ("codex",)),
    ("docker_desktop", "docker-desktop", ("docker", "Dock")),
    ("simctl_boot", "simctl-boot", ("simctl",)),
    ("lease_guard", "lease-guard", ("kill",)),
)
ONLY_WITHOUT_DENY = {"lease_guard"}
FAIL_CLOSED = {"release_guard"}


def triggered(command: str, needles: tuple[str, ...]) -> bool:
    """Whether the command holds a needle, ignoring case and the quotes and backslashes that split a word
    (`npm pub''lish`, `gh workflow run Release.yml`)."""
    if not needles:
        return True
    folded = command.replace("'", "").replace('"', "").replace("\\", "").lower()
    return any(needle in command or needle.lower() in folded for needle in needles)


def unfinished(name: str, why: str) -> str:
    return (f"{name} could not finish checking this command ({why}), and it names a release, publish, visibility or "
            "access step, so it is refused. Run the release step on its own, as one plain command, and retry.")


def decide(data: dict, budget: float = BUDGET):
    command = hook_io.command_of(data)
    if command is None:
        return None
    hook_io.set_budget(budget)
    denies, asks, ran = [], [], set()
    for module, name, needles in CHECKS:
        if not triggered(command, needles) or (denies and module in ONLY_WITHOUT_DENY):
            continue
        if (hook_io.remaining() or 0) <= 0:
            hook_io.log("guard.log", f"bash-guard budget spent before {name}")
            denies += [unfinished(n, "the hook's time was spent") for m, n, needles in CHECKS
                       if m in FAIL_CLOSED and triggered(command, needles) and n not in ran]
            break
        ran.add(name)
        try:
            decision = importlib.import_module(module).check(data)
        except Exception as error:  # noqa: BLE001 - fail open, check by check, but not the release guard
            hook_io.log("guard.log", f"{name} error {error!r}")
            if module in FAIL_CLOSED:
                denies.append(unfinished(name, f"it failed: {error!r}"))
            continue
        if decision:
            (denies if decision[0] == "deny" else asks).append(decision[1])
    if denies:
        return hook_io.deny("\n\n".join(denies))
    if asks:
        return hook_io.ask("\n\n".join(asks))
    return None


def guard(data: dict):
    """The hook: the checks' decision, then, for a command that is not denied, the lifecycle entries of
    `lifecycle.PreToolUse` in the machine settings (hooks/lifecycle.py): a rewriter's answer becomes the call's
    `updatedInput` beside the decision (hook_io.Answer), and the observers see the call. Neither changes the
    decision, and a deny is never rewritten."""
    decision = decide(data)
    updated = None
    try:
        lifecycle = hook_io.config().get("lifecycle")
        if not (decision and decision[0] == "deny") and isinstance(lifecycle, dict) and lifecycle.get("PreToolUse"):
            module = importlib.import_module("lifecycle")
            updated = module.rewrite(data, hook_io.remaining())
            module.observe(data, hook_io.remaining())
    except Exception as error:  # noqa: BLE001 - a lifecycle entry never costs the decision
        hook_io.log("guard.log", f"lifecycle error {error!r}")
    return hook_io.Answer(decision, updated) if updated is not None else decision


if __name__ == "__main__":
    sys.exit(hook_io.run("bash-guard", guard))
