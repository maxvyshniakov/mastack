#!/usr/bin/env python3
"""Codex credits guard, a Claude Code PreToolUse[Bash] check.

Once the weekly Codex limit is used up, every Codex run is billed to credits. On 2026-11-13 an orchestrating session
ran four `codex exec` reviews with Sol at 100% used: models.toml said the review role needs 15% left, and nothing
checked it.

Denies a headless Codex run, `codex exec` (or `codex e`) and `codex review`, by name or path, after Codex's global
options, in chains, pipes, compound commands, command substitutions and `sh|bash|zsh -c` scripts, while the weekly
limit has less left than the review role's Codex choice needs in models.toml (`when.limit.codex_weekly`), or Codex
reports the limit reached. The refusal names the share left, the threshold, what `role review` picks instead and
the owner's override: `MASTACK_ALLOW_CREDITS=1` in that command's environment prefix (`MASTACK_ALLOW_CREDITS=1 codex
exec ...` or through `env`), which passes and is logged to guard.log.

The limit is read as `bin/role` reads it (hooks/model_roles.py) and the read is reused for CACHE_SECONDS. A command
that runs no model passes without a read: `which codex`, `codex --version`, `codex exec --help`, `codex app-server`,
`codex login`, a path or text containing "codex". Without a codex on PATH, a table without a Codex threshold, a read
that fails or takes longer than the hook's budget allows, the command passes and nothing is said.
"""
from __future__ import annotations

import shlex
import sys

import hook_io

CACHE_SECONDS = 300
READ_SECONDS = 5.0  # at most; the hook's budget may leave less
OVERRIDE = "MASTACK_ALLOW_CREDITS=1"
RUNS = {"exec", "e", "review"}
# Codex's global options that take a value: the subcommand is the first word that is neither one nor its value.
VALUE_OPTIONS = {"-c", "--config", "-m", "--model", "-p", "--profile", "-C", "--cd", "-s", "--sandbox", "-a",
                 "--ask-for-approval", "-i", "--image", "--enable", "--disable", "--add-dir", "--local-provider"}
DISPLAY = {"-h", "--help", "-V", "--version"}


def runs_model(args) -> bool:
    """Whether `codex ARGS` starts a headless run: exec, its alias e, or review, not asked only for help."""
    index = 0
    while index < len(args):
        word = args[index].literal
        if word is None or word in DISPLAY:
            return False
        if word in VALUE_OPTIONS:
            index += 2
        elif word.startswith("-"):
            index += 1
        else:
            return word in RUNS and not any(w.literal in DISPLAY for w in args[index + 1:])
    return False


def headless_runs(command: str):
    """(shown command, overridden) for each headless Codex run in the command."""
    import slot_label
    import unguarded_sequence as shell
    for words in slot_label.simple_commands(shell, command, whole=True):
        own = shell.unwrap(words)
        if not own or (own[0].literal or "").rsplit("/", 1)[-1] != "codex" or not runs_model(own[1:]):
            continue
        prefix = words[:len(words) - len(own)]
        yield shell.show(own), any(word.raw == OVERRIDE for word in prefix)


def check(data: dict):
    command = hook_io.command_of(data)
    if command is None or "codex" not in command:
        return None
    import unguarded_sequence as shell
    try:
        runs = list(headless_runs(command))
    except (shell.Unreadable, ValueError, IndexError, StopIteration, RecursionError):
        return None
    blocked = [shown for shown, overridden in runs if not overridden]
    if not runs:
        return None
    if not blocked:
        hook_io.log("guard.log", f"codex-credits override command={command!r}")
        return None
    import model_roles
    try:
        table = model_roles.load()
        need = model_roles.codex_threshold(table, "review")
    except model_roles.TableError:
        return None
    if need is None:
        return None
    try:
        quota = model_roles.codex_weekly(timeout=hook_io.timeout(READ_SECONDS), max_age=CACHE_SECONDS)
    except hook_io.OutOfTime:
        return None
    why = model_roles.unmet("codex_weekly", need, quota)
    if quota.error is not None or why is None:
        return None
    choice, _, _ = model_roles.resolve(table, "review", None, read=lambda name: quota if name == "codex_weekly"
                                       else model_roles.Quota(error="not read by the hook"))
    fallback = (f"`role review` picks {choice.model} ({choice.id}), effort {choice.effort}: "
                f"`{shlex.join(next(iter(choice.argv.values()), []))}`" if choice
                else "`role review` finds no other choice")
    return hook_io.deny(
        "codex-credits denied this command: past the weekly Codex limit every run is billed to credits.\n"
        + "\n".join(f"- `{shown}`" for shown in dict.fromkeys(blocked)) + "\n"
        f"Weekly limit: {why} (the review role in models.toml).\n"
        f"Instead: {fallback}. For another role or with your implementer's family: "
        "`role <role> [--implementer-family F]` (bin/role in mastack).\n"
        f"Only when the owner said to spend credits: prefix the command with `{OVERRIDE}`.")


if __name__ == "__main__":
    sys.exit(hook_io.run("codex-credits", check))
