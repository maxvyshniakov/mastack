#!/usr/bin/env python3
"""Slot label guard, a Claude Code PreToolUse[Bash] check.

Everyone who shares the machine reads the labels on the slotfather dashboard to decide whether to wait for a
lease or reprioritize it, and `slotfather run` without --label takes the directory's name: the queue then showed
`scratchpad`, `desktop` and `mastack` for unrelated work.

Denies a `slotfather run` (by name or path, in chains, pipes, compound commands, command substitutions and
`sh|bash|zsh -c` scripts) whose --label (or -l) is missing, equals the basename of the directory it runs in (the
session's cwd, followed through literal `cd` steps), or is made only of generic words (`scratchpad`, `tmp`, `test`,
`run`, `check` ...), is empty, or still holds a placeholder such as `<ticket>`. The message gives the format `<task or ticket> <what it does>` and an example built from the
command: the task from --ticket or `--meta lane=`, what it does from the leased command's own words.

Wrappers that lease on their own (Lanefather, repo-kit, a project's verify script) start slotfather themselves with
their own label, so their commands hold no `slotfather run` and pass. A label in a variable is not judged. Read like
the unguarded-sequence guard reads the shell; a command it cannot parse passes.
"""
from __future__ import annotations

import os
import re
import sys

import hook_io

GENERIC = {"scratchpad", "scratch", "tmp", "temp", "test", "tests", "testing", "run", "runs", "check", "checks",
           "build", "builds", "job", "task", "work", "wip", "misc", "stuff", "foo", "bar", "x", "it", "cmd",
           "command", "slotfather", "lease", "slot", "verify", "gate", "suite", "all", "measure", "bench"}
SHELLS = {"sh", "bash", "zsh"}
# Programs and verbs that only start the real work: `uv run pytest` is pytest, `python3 tools/check.py` is check.
RUNNERS = {"python", "python3", "node", "bun", "bunx", "npm", "npx", "pnpm", "yarn", "uv", "uvx", "deno",
           "sh", "bash", "zsh"}
RUN_VERBS = {"run", "exec", "x"}
RUN_VALUE_OPTIONS = {"-n", "--slots", "-l", "--label", "--meta", "--priority", "--ticket", "--wait"}


def simple_commands(shell, command: str):
    """The words of every simple command, in order, through compound commands, substitutions and `sh -c`."""
    import pgrep_self_match
    for words, _ in pgrep_self_match.walk(shell, shell.parse(hook_io.strip_heredocs(command))):
        own = shell.unwrap(words)
        name = (own[0].literal or "").rsplit("/", 1)[-1] if own else ""
        if name in SHELLS:
            literals = [w.literal or "" for w in own[1:]]
            # -c alone or in a short-option cluster (`bash -lc`); the script is the first word after the options.
            at = next((i for i, w in enumerate(literals) if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", w)), None)
            script = next((own[1 + i] for i in range(at + 1, len(literals)) if not literals[i].startswith("-")),
                          None) if at is not None else None
            if script is not None and script.literal is not None:
                yield from simple_commands(shell, script.literal)
                continue
        yield own


def run_options(args):
    """(label word or None when absent, ticket, lane, leased command words) of `slotfather run ARGS`."""
    label, ticket, lane, index = None, None, None, 0
    while index < len(args):
        option = args[index].literal
        if option == "--":
            index += 1
            break
        if option in RUN_VALUE_OPTIONS and index + 1 < len(args):
            value = args[index + 1]
            if option in ("-l", "--label"):
                label = value
            elif option == "--ticket":
                ticket = value.literal
            elif option == "--meta" and (value.literal or "").startswith("lane="):
                lane = value.literal.split("=", 1)[1]
            index += 2
        elif option is not None and option.startswith("-"):
            index += 1
        else:
            break
    return label, ticket, lane, args[index:]


def stem(word: str) -> str:
    return os.path.basename(word.rstrip("/")).split(".")[0]


def what_it_does(shell, words) -> str:
    """A short name for the leased command: `python3 -m unittest discover` -> unittest-discover, `cargo test` ->
    cargo-test, `uv run pytest -q` -> pytest, `./verify.sh --checks x` -> verify."""
    words = [w.literal for w in shell.unwrap(words)]
    found, index = [], 0
    while index < len(words) and len(found) < 2:
        word = words[index]
        if word is None:
            break
        name = stem(word)
        if not found and name in RUNNERS:
            if index + 2 < len(words) and words[index + 1] == "-m":
                index += 2
                continue
            index += 1
            # the runner's own flags (`python3 -u`) and verbs (`uv run`)
            while index < len(words) and (words[index] in RUN_VERBS or (
                    words[index] and re.fullmatch(r"-[A-Za-ln-z]+", words[index]))):
                index += 1
            continue
        if word.startswith("-") or not re.search(r"[A-Za-z0-9]", name):
            break
        found.append(name)
        index += 1
    return "-".join(found) or "<what it does>"


def refusal(label: str, cwd: str | None) -> str | None:
    if label is None or label is False:
        return "has no --label, so the queue shows the directory's name"
    if not label.strip():
        return "has an empty --label"
    placeholder = re.search(r"<[^>]*>", label)
    if placeholder:
        return f"labels it `{label}`, which still holds the placeholder `{placeholder.group(0)}`"
    if cwd and label.strip().lower() == os.path.basename(cwd.rstrip("/")).lower():
        return f"labels it `{label}`, but `{label}` is the directory's name"
    parts = [part for part in re.split(r"[\s\-_./:]+", label.strip().lower()) if part]
    if all(part in GENERIC for part in parts):
        return f"labels it `{label}`, but `{label}` is only generic words"
    return None


def check(data: dict):
    command = hook_io.command_of(data)
    if command is None or "slotfather" not in command:
        return None
    import unguarded_sequence as shell
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    found = []
    try:
        for words in simple_commands(shell, command):
            name = (words[0].literal or "").rsplit("/", 1)[-1] if words else ""
            if name == "cd" and len(words) > 1 and words[1].literal and cwd is not None:
                cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(words[1].literal)))
            if name != "slotfather" or len(words) < 2 or words[1].literal != "run":
                continue
            label_word, ticket, lane, leased = run_options(words[2:])
            label = False if label_word is None else label_word.literal
            if label is None:
                continue  # a variable: not judged
            why = refusal(label, cwd)
            if why:
                example = f'--label "{ticket or lane or "<ticket>"} {what_it_does(shell, leased)}"'
                found.append((shell.show(words), why, example))
    except (shell.Unreadable, ValueError, IndexError, StopIteration, RecursionError):
        return None
    if not found:
        return None
    lines = [f"- `{shown}` {why}. Example: `{example}`." for shown, why, example in dict.fromkeys(found)]
    return hook_io.deny(
        "slot-label denied this command: everyone reads labels on the slotfather dashboard to decide whether to "
        "wait for a lease or reprioritize it, so a label says whose task it is and what it does.\n"
        + "\n".join(lines) + "\n"
        'Fix: pass --label "<task or ticket> <what it does>" (not the directory\'s name, not a bare word like '
        "`test`). Lanefather, repo-kit and project verify wrappers label their own leases; run them directly.")


if __name__ == "__main__":
    sys.exit(hook_io.run("slot-label", check))
