#!/usr/bin/env python3
"""pgrep self-match guard, a Claude Code PreToolUse[Bash] check.

`pgrep -f PATTERN` and `pkill -f PATTERN` match PATTERN against every process's full command line, and the shell
that runs a Bash tool command carries that whole command, PATTERN included, in its own. macOS pgrep leaves out
only itself and its ancestors (Linux pgrep only itself), so a wait loop finds every other agent shell whose
command holds the same text: an earlier wait loop on the same pattern, a monitor, and on Linux its own shell. Each
new loop then keeps the ones before it alive (2026-11-04: 25 loops of one session ran 10 to 35 hours), and
`pkill -f PATTERN` signals those shells.

Denies a pgrep or pkill with -f (also in a short-option cluster such as -fl) whose literal PATTERN, read as a
regular expression, matches the command's own text as the shell holds it (`/bin/zsh -c <command>`). Bracketing
one character (`[l]ane check X`) is the fix: the pattern no longer matches its own text. A pattern in a variable
or a substitution is not seen, nor is one with -x (exact match) or -v (inverted); pgrep without -f matches
process names only. Read like the unguarded-sequence guard reads the shell, and a command it cannot parse passes.
"""
from __future__ import annotations

import re
import sys

import hook_io

PROGRAMS = {"pgrep", "pkill"}
WITH_VALUE = {"-F", "-G", "-g", "-P", "-t", "-U", "-u", "-s", "-J", "-d", "--signal"}
SIGNAL = re.compile(r"-(\d+|[A-Z][A-Z0-9+-]*|SIG[A-Za-z0-9+-]+)")
SHELL = "/bin/zsh -c "


def walk(shell, lst):
    """Every simple command of a parsed list, in compound commands and substitutions too."""
    for and_or, _ in lst:
        for pipeline, _ in and_or:
            for command in pipeline:
                yield from inner(shell, command)


def inner(shell, command):
    kind = command[0]
    if kind == "simple":
        yield command[1]
        for word in command[1]:
            for sub in word.subs:
                yield from walk(shell, shell.parse(hook_io.strip_heredocs(sub)))
    elif kind in ("group", "subshell", "function"):
        yield from walk(shell, command[1])
    elif kind == "if":
        for condition, body in command[1]:
            yield from walk(shell, condition)
            yield from walk(shell, body)
        yield from walk(shell, command[2] or [])
    elif kind == "loop":
        yield from walk(shell, command[1])
        yield from walk(shell, command[2])
    elif kind == "case":
        for body in command[1]:
            yield from walk(shell, body)


def patterns(words) -> list[str]:
    """The literal patterns of a `pgrep -f` or `pkill -f`; [] when it matches names only, exactly or inverted."""
    args = words[1:]
    if args and words[0].literal.rsplit("/", 1)[-1] == "pkill" and SIGNAL.fullmatch(args[0].literal or ""):
        args = args[1:]
    full, found, index = False, [], 0
    while index < len(args):
        value = args[index].literal
        if value is not None and value in WITH_VALUE:
            index += 2
            continue
        if value is not None and re.fullmatch(r"-[A-Za-z]+", value):
            if "x" in value or "v" in value:
                return []
            full = full or "f" in value
        elif value is not None and value not in ("--",) and not value.startswith("--"):
            found.append(value)
        index += 1
    return found if full else []


def matches(pattern: str, text: str) -> bool:
    try:
        return re.search(pattern, text) is not None
    except (re.error, RecursionError):
        return False


def check(data: dict):
    command = hook_io.command_of(data)
    if command is None or ("pgrep" not in command and "pkill" not in command):
        return None
    import unguarded_sequence as shell
    try:
        parsed = shell.parse(hook_io.strip_heredocs(command))
        found = []
        for words in walk(shell, parsed):
            own = shell.unwrap(words)
            if not own or (own[0].literal or "").rsplit("/", 1)[-1] not in PROGRAMS:
                continue
            for pattern in patterns(own):
                if matches(pattern, SHELL + command):
                    found.append((shell.show(own), pattern))
    except (shell.Unreadable, ValueError, IndexError, StopIteration, RecursionError):
        return None
    if not found:
        return None
    lines = [f"- `{shown}`: the pattern {pattern!r} matches this command's own text." for shown, pattern in
             dict.fromkeys(found)]
    return hook_io.deny(
        "pgrep-self-match denied this command: `pgrep -f` and `pkill -f` match every process's full command line, "
        "and every agent shell that runs a command holding this pattern carries it in its own (an earlier wait loop, "
        "a monitor, on Linux this very shell), so a wait loop keeps finding them and never ends, and pkill signals "
        "them.\n" + "\n".join(lines) + "\n"
        "Fix: bracket one character so the pattern stops matching its own text (`pgrep -f \"[l]ane check X\"`), "
        "or wait on a pid (`while kill -0 $pid; do sleep 15; done`), on a file, or on the tool's own completion "
        "notification (run it with run_in_background).")


if __name__ == "__main__":
    sys.exit(hook_io.run("pgrep-self-match", check))
