#!/usr/bin/env python3
"""Simulator boot guard, a Claude Code PreToolUse[Bash] check: boot iOS simulators only under junkfather.

A simulator an agent boots stays booted after the agent ends, holding gigabytes of memory, unless something shuts
it down. junkfather does: `junkfather own --kind simulator -- xcrun simctl boot UDID` runs the boot, owns the booted
device, and shuts it down when the session ends or the TTL (`--ttl`) runs out.

Denies `xcrun simctl boot` and `xcrun simctl bootstatus -b` (also `simctl` by path, with xcrun's and simctl's own
options before the subcommand) in chains, pipes, compound commands, command substitutions and `sh|bash|zsh -c`
scripts, unless junkfather runs it: `junkfather own --kind simulator ... -- xcrun simctl boot UDID`. A
`junkfather own` without `--kind simulator` around a boot is denied too: it owns only the boot command, which exits
at once and leaves the simulator running. The message shows the wrapped form built from the command.

Other simctl subcommands pass (`shutdown`, `list`, `install`, `launch` ...). When junkfather is not installed
($MASTACK_JUNKFATHER or `junkfather` in hooks.json, else PATH, else ~/.local/bin/junkfather) every command passes,
since there is nothing to wrap it in. Read like the unguarded-sequence guard reads the shell; a command it cannot
parse passes.
"""
from __future__ import annotations

import os
import re
import shutil
import sys

import hook_io
import shell

SHELLS = {"sh", "bash", "zsh"}
XCRUN_VALUE = {"--sdk", "-sdk", "--toolchain", "-toolchain"}
XCRUN_LOOKS = {"-f", "--find", "-h", "--help", "--version", "--show-sdk-path", "--show-sdk-version",
               "--show-sdk-platform-path", "--show-sdk-platform-version", "--show-sdk-build-version"}
SIMCTL_VALUE = {"--set", "--profiles"}
OWN_VALUE = {"--ttl", "--keep-for", "--label", "--lane", "--log", "--kind", "--agent"}


def junkfather() -> str | None:
    """$MASTACK_JUNKFATHER or `junkfather` in hooks.json when set (None when it is not executable), else PATH, else
    ~/.local/bin/junkfather, where its installer puts it."""
    configured = os.environ.get("MASTACK_JUNKFATHER") or hook_io.config().get("junkfather")
    if isinstance(configured, str) and configured:
        path = os.path.expanduser(configured)
        return path if os.access(path, os.X_OK) else None
    fallback = os.path.expanduser("~/.local/bin/junkfather")
    return shutil.which("junkfather") or (fallback if os.access(fallback, os.X_OK) else None)


def name_of(words) -> str:
    return (words[0].literal or "").rsplit("/", 1)[-1] if words else ""


def boots(words) -> bool:
    """`xcrun [options] simctl [options] boot ...`, `simctl boot ...` or `... bootstatus -b`."""
    index = 0
    if name_of(words) == "xcrun":
        index = 1
        while index < len(words):
            value = words[index].literal
            if value is None:
                return False
            if value in XCRUN_LOOKS:
                return False
            if value in XCRUN_VALUE:
                index += 2
            elif value.startswith("-"):
                index += 1
            else:
                break
        if index >= len(words) or (words[index].literal or "").rsplit("/", 1)[-1] != "simctl":
            return False
    elif name_of(words) != "simctl":
        return False
    index += 1
    while index < len(words):
        value = words[index].literal
        if value is None:
            return False
        if value in SIMCTL_VALUE:
            index += 2
        elif value.startswith("-"):
            index += 1
        else:
            break
    if index >= len(words):
        return False
    verb = words[index].literal
    rest = [w.literal for w in words[index + 1:]]
    return verb == "boot" or (verb == "bootstatus" and any(
        w is not None and re.fullmatch(r"-[A-Za-z]*b[A-Za-z]*", w) for w in rest))


def own_parts(words):
    """(kind, wrapped words) of `junkfather own [options] [--] CMD...`, or None for another command."""
    if name_of(words) != "junkfather" or len(words) < 2 or words[1].literal != "own":
        return None
    kind, index = None, 2
    while index < len(words):
        value = words[index].literal
        if value == "--":
            index += 1
            break
        if value is not None and value.startswith("--kind="):
            kind = value.split("=", 1)[1]
            index += 1
        elif value in OWN_VALUE:
            if value == "--kind" and index + 1 < len(words):
                kind = words[index + 1].literal
            index += 2
        elif value is not None and value.startswith("-"):
            index += 1
        else:
            break
    return kind, words[index:]


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
    for words in _walk(shell.read(command)):
        own = shell.unwrap(words)
        script = _script(own) if name_of(own) in SHELLS else None
        if script is not None:
            yield from simple_commands(script)
        else:
            yield own


def wrapped(words) -> list:
    """The boots a command holds: itself, or behind `sh -c`."""
    if boots(words):
        return [words]
    script = _script(words) if name_of(words) in SHELLS else None
    if script is None:
        return []
    return [boot for inner in simple_commands(script) for boot in wrapped(inner)]


def _script(words) -> str | None:
    literals = [w.literal or "" for w in words[1:]]
    at = next((i for i, w in enumerate(literals) if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", w)), None)
    if at is None:
        return None
    script = next((words[1 + i] for i in range(at + 1, len(literals)) if not literals[i].startswith("-")), None)
    return script.literal if script is not None else None


def findings(command: str):
    for words in simple_commands(command):
        if boots(words):
            yield shell.show(words), "boots a simulator nothing shuts down", words
            continue
        parts = own_parts(words)
        if parts is None or parts[0] == "simulator":
            continue
        for boot in wrapped(parts[1]):
            yield (shell.show(words), f"runs the boot under `junkfather own` without `--kind simulator`, so it owns "
                   "only the boot command, which exits at once and leaves the simulator running", boot)


def check(data: dict):
    command = hook_io.command_of(data)
    if command is None or "simctl" not in command or junkfather() is None:
        return None
    try:
        found = list(findings(command))
    except (shell.Unreadable, ValueError, IndexError, StopIteration, RecursionError):
        return None
    if not found:
        return None
    lines = list(dict.fromkeys(
        f"- `{shown}` {why}. Run: `junkfather own --kind simulator --label \"<what it is for>\" -- "
        f"{' '.join(w.raw for w in boot)}`." for shown, why, boot in found))
    return hook_io.deny(
        "simctl-boot denied this command: a simulator booted outside junkfather stays booted after the session "
        "ends. `junkfather own --kind simulator [--ttl 2h] [--label L] -- xcrun simctl boot <udid>` owns the "
        "booted device and shuts it down when the session ends or its TTL runs out.\n" + "\n".join(lines))


if __name__ == "__main__":
    sys.exit(hook_io.run("simctl-boot", check))
