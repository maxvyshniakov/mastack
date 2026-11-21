#!/usr/bin/env python3
"""Codex credits guard, a Claude Code PreToolUse[Bash] check.

Once the weekly Codex limit is used up, every Codex run is billed to credits. On 2026-11-13 an orchestrating session
ran four `codex exec` reviews with Sol at 100% used: models.toml said the review role needs 15% left, and nothing
checked it.

Denies a headless Codex run, `codex exec` (or `codex e`) and `codex review`, while the weekly limit has less left
than the review role's Codex choice needs in models.toml (`when.limit.codex_weekly`), or Codex reports the limit
reached. It finds the run by name or path, after Codex's global options (an unknown option's value or a variable
is looked past), in chains, pipes, compound commands, command substitutions, `sh|bash|zsh -c` scripts and `eval`,
and behind wrappers: env, nohup and the others unguarded_sequence.unwrap knows, `timeout`/`gtimeout`, `xargs`,
`npx`/`bunx`/`pnpx` of `codex` or `@openai/codex`, and the leased command after `--` of `slotfather run` and
`junkfather own`. It cannot see a run behind a shell alias or function, a program name in a variable (`$CODEX
exec`), or inside a script the command starts.

The refusal names the share left, the threshold, what `bin/role review` picks instead, how to read the limit again,
and the owner's override: `MASTACK_ALLOW_CREDITS=1` before the run in that same command (`MASTACK_ALLOW_CREDITS=1
codex exec ...`, through `env` or before a wrapper), which passes and logs the program and subcommand to guard.log.

The limit is read as `bin/role` reads it (hooks/model_roles.py) and the read is reused for CACHE_SECONDS, or until
the window's reset time. A command that runs no model passes without a read: `which codex`, `codex --version`,
`codex exec --help`, `codex app-server`, `codex login`, a path or text containing "codex". Without a codex on PATH, a
table without a Codex threshold, a read that fails or takes longer than the hook's budget allows, the command passes
and nothing is said.
"""
from __future__ import annotations

import shlex
import sys
import time

import hook_io
import shell
from vocabulary import SHELLS

CACHE_SECONDS = 300
READ_SECONDS = 5.0  # at most; the hook's budget may leave less
OVERRIDE = "MASTACK_ALLOW_CREDITS=1"
RUNS = {"exec", "e", "review"}
# Subcommands that start no headless run: the first of these ends the search.
OTHERS = {"app-server", "login", "logout", "mcp", "mcp-server", "completion", "apply", "a", "sandbox", "debug",
          "cloud", "features", "help", "proto", "resume", "fork", "generate-ts", "responses-api-proxy",
          "stdio-to-uds", "execpolicy"}
# Codex's global options that take a value, skipped with it; an unknown option's value is looked past.
VALUE_OPTIONS = {"-c", "--config", "-m", "--model", "-p", "--profile", "-C", "--cd", "-s", "--sandbox", "-a",
                 "--ask-for-approval", "-i", "--image", "--enable", "--disable", "--add-dir", "--local-provider"}
DISPLAY = {"-h", "--help", "-V", "--version"}
TIMEOUT_VALUES = {"-s", "--signal", "-k", "--kill-after"}
XARGS_VALUES = {"-n", "-L", "-P", "-I", "-J", "-E", "-d", "-s", "-a", "-R", "-S"}
NPX = {"npx", "bunx", "pnpx"}
NPX_VALUES = {"-p", "--package", "-c", "--call"}
CODEX_PACKAGES = {"codex", "@openai/codex"}
LEASED = {"slotfather": "run", "junkfather": "own"}


def _walk(lst):
    for and_or, _ in lst:
        for pipeline, _ in and_or:
            for command in pipeline:
                yield from _inner(command)


def _inner(command):
    kind = command[0]
    if kind == "simple":
        yield command[1]
        for word in command[1]:
            for sub in word.subs:
                yield from _walk(shell.read(sub))
    elif kind in ("group", "subshell", "function"):
        yield from _walk(command[1])
    elif kind == "if":
        for condition, body in command[1]:
            yield from _walk(condition)
            yield from _walk(body)
        yield from _walk(command[2] or [])
    elif kind == "loop":
        yield from _walk(command[1])
        yield from _walk(command[2])
    elif kind == "case":
        for body in command[1]:
            yield from _walk(body)


def simple_commands(command: str):
    """Every simple command's words (with leading assignments and wrappers), through compound commands,
    substitutions and `sh -c`."""
    import re
    for words in _walk(shell.read(command)):
        own = shell.unwrap(words)
        name = (own[0].literal or "").rsplit("/", 1)[-1] if own else ""
        if name in SHELLS:
            literals = [w.literal or "" for w in own[1:]]
            at = next((i for i, w in enumerate(literals) if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", w)), None)
            script = next((own[1 + i] for i in range(at + 1, len(literals)) if not literals[i].startswith("-")),
                          None) if at is not None else None
            if script is not None and script.literal is not None:
                yield from simple_commands(script.literal)
                continue
        yield words


def name_of(word) -> str:
    return (word.literal or "").rsplit("/", 1)[-1]


def package_name(spec: str) -> str:
    """`@openai/codex@1.2` -> `@openai/codex`, `codex@latest` -> `codex`."""
    scoped = spec.startswith("@")
    return ("@" if scoped else "") + spec[scoped:].split("@", 1)[0]


def runs_model(args) -> bool:
    """Whether `codex ARGS` starts a headless run: exec, its alias e, or review, not asked only for help."""
    index = 0
    while index < len(args):
        word = args[index].literal
        if word in DISPLAY:
            return False
        if word in VALUE_OPTIONS:
            index += 2
            continue
        if word in RUNS:
            return not any(w.literal in DISPLAY for w in args[index + 1:])
        if word in OTHERS:
            return False
        index += 1  # an option, an unknown option's value, a variable or a prompt
    return False


def after_options(args, values: set[str]) -> list:
    """`args` without the leading options, and the values of those in `values`."""
    index = 0
    while index < len(args) and (args[index].literal or "").startswith("-"):
        index += 2 if args[index].literal in values else 1
    return args[index:]


def codex_word(shell, own):
    """(the `codex` word `own` runs through the wrappers it knows, the words after it), or None."""
    while own:
        name, rest = name_of(own[0]), own[1:]
        if name == "codex":
            return own[0], rest
        if name in ("timeout", "gtimeout"):
            own = shell.unwrap(after_options(rest, TIMEOUT_VALUES)[1:])
        elif name == "xargs":
            own = shell.unwrap(after_options(rest, XARGS_VALUES))
        elif name in NPX:
            rest = after_options(rest, NPX_VALUES)
            if not rest or package_name(rest[0].literal or "") not in CODEX_PACKAGES:
                return None
            return rest[0], rest[1:]
        elif name in LEASED and rest and rest[0].literal == LEASED[name]:
            ends = [i for i, word in enumerate(rest) if word.literal == "--"]
            if not ends:
                return None
            own = shell.unwrap(rest[ends[0] + 1:])
        else:
            return None
    return None


def headless_runs(command: str, depth: int = 0):
    """(program and subcommand, shown command, overridden) for each headless Codex run in the command."""
    for words in simple_commands(command):
        own = shell.unwrap(words)
        if own and name_of(own[0]) == "eval":
            if depth < 3:
                outer = any(word.raw == OVERRIDE for word in words[:len(words) - len(own)])
                text = " ".join(word.literal for word in own[1:] if word.literal is not None)
                for head, shown, overridden in headless_runs(text, depth + 1):
                    yield head, shown, overridden or outer
            continue
        found = codex_word(shell, own)
        if found is None or not runs_model(found[1]):
            continue
        at = next(i for i, word in enumerate(words) if word is found[0])
        subcommand = next((w.literal for w in found[1] if w.literal in RUNS), "")
        yield f"codex {subcommand}", shell.show(own), any(word.raw == OVERRIDE for word in words[:at])


def check(data: dict):
    command = hook_io.command_of(data)
    if command is None or "codex" not in command:
        return None
    try:
        runs = list(headless_runs(command))
    except (shell.Unreadable, ValueError, IndexError, StopIteration, RecursionError):
        return None
    if not runs:
        return None
    for head, _, overridden in runs:
        if overridden:
            hook_io.log("guard.log", f"codex-credits override: {head} cwd={data.get('cwd')}")
    blocked = [shown for _, shown, overridden in runs if not overridden]
    if not blocked:
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
    return hook_io.deny(refusal(table, quota, why, blocked))


def refusal(table: dict, quota, why: str, blocked: list[str]) -> str:
    import model_roles
    role = str(model_roles.ROOT / "bin" / "role")
    choice, _, _ = model_roles.resolve(table, "review", None, read=lambda name: quota if name == "codex_weekly"
                                       else model_roles.Quota(error="not read by the hook"))
    if choice:
        fallback = (f"`{role} review` picks {choice.model} ({choice.id}), effort {choice.effort}: "
                    f"`{shlex.join(next(iter(choice.argv.values()), []))}`; with `--implementer-family <family>` it "
                    "may pick another")
    else:
        fallback = f"`{role} review` finds no other choice"
    minutes = max(0, round((time.time() - quota.read_at) / 60))
    return ("codex-credits denied this command: past the weekly Codex limit every run is billed to credits.\n"
            + "\n".join(f"- `{shown}`" for shown in dict.fromkeys(blocked)) + "\n"
            f"Weekly limit: {why} (the review role in models.toml), read {minutes} min ago; "
            f"`{role} review` reads it again.\n"
            f"Instead: {fallback}. For another role: `{role} <role>`.\n"
            f"Only when the owner said to spend credits: prefix the command with `{OVERRIDE}`.")


if __name__ == "__main__":
    sys.exit(hook_io.run("codex-credits", check))
