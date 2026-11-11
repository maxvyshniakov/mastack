#!/usr/bin/env python3
"""Lease guard, a Claude Code PreToolUse[Bash] check: never kill another holder's lease.

The owner's rule: an agent does not kill, stop or signal a process that runs inside another holder's slotfather
lease. Denies a `kill`, `pkill` or `killall` (also through `xargs`) whose target is such a process: the holder
(`slotfather run`) or one of its descendants, or a process that left its tree and carries its SLOTFATHER_LEASE,
as `slotfather status --json --pid PID` reports them. Before deciding it compares the process's start time with
the one slotfather saw, so a pid reused while it looked is not taken for the lease's process.

Targets: literal pids, process groups (`-PGID`; `-1` is every process), `$(pgrep ...)`, `$(lsof -t ...)` and
`$(cat FILE)` substitutions, `pgrep|lsof|cat ... | xargs kill`, and the processes `pkill` and `killall` would match
(on macOS `killall -s` lists what `killall` would signal, `-u USER` alone included; `pkill` is pgrep with the same
matching options). Every pid is asked; a set too large to ask one by one keeps the pids in a lease's tree or carrying
a SLOTFATHER_LEASE, the only ones slotfather can place in a lease. Signal 0 and `-l` only look. A target held in a
variable is not seen: misses are preferred to false positives, a command this parser cannot read passes, and so does everything
when slotfather is not installed or does not answer.

The caller owns a lease when it runs under it (the same SLOTFATHER_LEASE) or when the lease's `lane` metadata names
the lane whose worktree the caller works in (the lane tool's records, `lane_records` in hooks.json). The session's
main thread (hook input without `agent_id`), which starts lanes, lands and measurements, also owns every lease whose
`session` metadata is its session and every lease whose holder descends from its Claude Code process (CLAUDE_PID,
else the nearest `claude` ancestor): its subagents share both, so a subagent owns neither. A lease without a lane is also the caller's when it
runs in the caller's worktree and names no other session. A lane tool that takes leases writes that metadata
(`slotfather run --meta lane=<id> --meta session=<id>`).

A command prefixed with LEASE_GUARD_OK="<reason>" that reaches another holder's lease is not denied but asked: the
permission card shows the reason and the leases, so the owner, not the agent that wrote the prefix, approves it
(auto mode shows a hook's ask too; a background subagent that cannot ask is denied). It is logged to guard.log.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

import hook_io

KILLERS = {"kill", "pkill", "killall"}
# Read-only commands whose output names the pids a kill gets.
PRODUCERS = {"pgrep", "lsof", "cat"}
SIGNAL = re.compile(r"-(\d+|[A-Z][A-Z0-9+-]*|SIG[A-Za-z0-9+-]+)")
XARGS_WITH_VALUE = {"-n", "-I", "-J", "-L", "-P", "-s", "-E", "-R", "-S"}
KILLALL_WITH_VALUE = {"-u", "-t", "-c"}
PKILL_WITH_VALUE = {"-F", "-G", "-g", "-P", "-t", "-U", "-u", "-s"}
PER_PID_LIMIT = 48  # pids asked one by one; above it, only those in a lease's tree


shell = None  # unguarded_sequence's shell reader, loaded once a command mentions kill


class Unresolved(Exception):
    """A target this guard cannot know before the command runs."""


def run(argv: list[str], timeout: float = 3) -> str:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=hook_io.timeout(timeout))
    except (OSError, subprocess.SubprocessError):
        raise Unresolved(" ".join(argv)) from None
    return result.stdout


def literal_args(words) -> list[str]:
    values = [word.literal for word in words]
    if any(value is None for value in values):
        raise Unresolved(" ".join(word.raw for word in words))
    return values


def name(word) -> str:
    return os.path.basename(word.literal or "")


def numbers(text: str) -> set[int]:
    return {int(token) for token in text.split() if token.isdigit()}


def produced(words) -> set[int]:
    """The pids a read-only producer prints: pgrep, lsof with -t, cat of a pid file."""
    words = shell.unwrap(words)
    if not words or name(words[0]) not in PRODUCERS:
        raise Unresolved(shell.show(words))
    args = literal_args(words[1:])
    program = name(words[0])
    if program == "lsof" and not any(a.startswith("-") and "t" in a[1:] and not a.startswith("--") for a in args):
        raise Unresolved("lsof without -t")
    if program == "cat":
        text = ""
        for path in args:
            try:
                with open(os.path.expanduser(path), encoding="utf-8", errors="replace") as handle:
                    text += handle.read(4096) + "\n"
            except OSError:
                raise Unresolved(path) from None
        return numbers(text)
    return numbers(run([program, *args]))


def substitution(word) -> set[int]:
    """The pids a `$(producer ...)` word expands to."""
    if len(word.subs) != 1 or word.text.strip("\0").strip():
        raise Unresolved(word.raw)
    parsed = shell.parse(hook_io.strip_heredocs(word.subs[0]))
    if len(parsed) != 1 or len(parsed[0][0]) != 1 or len(parsed[0][0][0][0]) != 1:
        raise Unresolved(word.raw)
    command = parsed[0][0][0][0][0]
    if command[0] != "simple":
        raise Unresolved(word.raw)
    return produced(command[1])


class Targets:
    def __init__(self):
        self.pids: set[int] = set()
        self.groups: set[int] = set()
        self.everything = False


def kill_targets(args, stdin=None) -> Targets | None:
    """What `kill ARGS` signals; None when it only looks (signal 0, -l)."""
    targets = Targets()
    index, signal = 0, None
    first = args[0].literal if args else None
    if first in ("-l", "-L"):
        return None
    if first in ("-s", "-n") and len(args) > 1:
        signal, index = args[1].literal, 2
    elif first and first != "--" and SIGNAL.fullmatch(first):
        signal, index = first[1:], 1
    if index < len(args) and args[index].literal == "--":
        index += 1
    if signal is None and first and first.startswith("-") and first != "--" and not SIGNAL.fullmatch(first):
        raise Unresolved(first)
    if signal in ("0", "SIG0"):
        return None
    for word in args[index:]:
        value = word.literal
        if value is None:
            targets.pids |= substitution(word)
        elif value.isdigit():
            targets.pids.add(int(value))
        elif re.fullmatch(r"-\d+", value):
            if value == "-1":
                targets.everything = True
            else:
                targets.groups.add(int(value[1:]))
        elif not value.startswith("%"):
            raise Unresolved(value)
    if stdin is not None:
        targets.pids |= stdin
    return targets


def pkill_targets(args) -> Targets | None:
    """The processes `pkill ARGS` matches: pgrep with its matching options."""
    values = literal_args(args)
    if values and SIGNAL.fullmatch(values[0]):
        values = values[1:]
    pgrep, index = [], 0
    while index < len(values):
        value = values[index]
        if value == "--signal":
            index += 2
            continue
        if value == "-I":  # pkill's confirmation prompt
            index += 1
            continue
        pgrep.append(value)
        if value in PKILL_WITH_VALUE and index + 1 < len(values):
            pgrep.append(values[index + 1])
            index += 1
        index += 1
    targets = Targets()
    targets.pids = numbers(run(["pgrep", *pgrep]))
    return targets


def killall_targets(args) -> Targets | None:
    """The processes macOS `killall ARGS` matches: by exact name, a regular expression with -m, -u and -t."""
    values = literal_args(args)
    names, filters, regex, index = [], [], False, 0
    while index < len(values):
        value = values[index]
        if value in ("-l", "-s", "-d", "-h", "-help", "-?"):
            return None  # lists or shows only
        if value in KILLALL_WITH_VALUE and index + 1 < len(values):
            if value == "-c":
                names.append(values[index + 1])
            else:
                filters += [value, values[index + 1]]
            index += 2
            continue
        if value == "-m":
            regex = True
        elif value == "-SIGNAL0" or value == "-0":
            return None
        elif not value.startswith("-"):
            names.append(value)
        index += 1
    targets = Targets()
    if sys.platform == "darwin":
        # macOS killall's own dry run: what it would signal, by its own matching (and `-u USER` alone: everything).
        listed = run(["killall", "-s", *[value for value in values if value != "-I"]])
        targets.pids = {int(pid) for pid in re.findall(r"^kill -\S+ (\d+)$", listed, re.M)}
        return targets
    for wanted in names or ([None] if filters else []):
        targets.pids |= numbers(run(["pgrep", *filters, *([] if regex or wanted is None else ["-x"]),
                                     *([wanted] if wanted is not None else [])]))
    return targets


def pipelines(lst):
    """Every pipeline of a parsed list, in compound commands and command substitutions too."""
    for and_or, _ in lst:
        for pipeline, _ in and_or:
            yield pipeline
            for command in pipeline:
                yield from inner(command)


def inner(command):
    kind = command[0]
    if kind == "simple":
        for word in command[1]:
            for sub in word.subs:
                yield from pipelines(shell.parse(hook_io.strip_heredocs(sub)))
    elif kind in ("group", "subshell", "function"):
        yield from pipelines(command[1])
    elif kind == "if":
        for condition, body in command[1]:
            yield from pipelines(condition)
            yield from pipelines(body)
        yield from pipelines(command[2] or [])
    elif kind == "loop":
        yield from pipelines(command[1])
        yield from pipelines(command[2])
    elif kind == "case":
        for body in command[1]:
            yield from pipelines(body)


def kills(command: str) -> list[tuple[str, Targets]]:
    """Each kill in the command, as written, with what it signals; unresolvable ones are left out."""
    found = []
    for pipeline in pipelines(shell.parse(hook_io.strip_heredocs(command))):
        for index, element in enumerate(pipeline):
            if element[0] != "simple":
                continue
            words = shell.unwrap(element[1])
            if not words:
                continue
            program, stdin = name(words[0]), None
            if program == "xargs":
                rest = words[1:]
                while rest and (rest[0].literal or "").startswith("-"):
                    rest = rest[2:] if rest[0].literal in XARGS_WITH_VALUE else rest[1:]
                if not rest or name(rest[0]) != "kill" or index == 0 or pipeline[index - 1][0] != "simple":
                    continue
                try:
                    stdin = produced(pipeline[index - 1][1])
                except (Unresolved, shell.Unreadable):
                    continue
                words, program = rest, "kill"
            if program not in KILLERS:
                continue
            try:
                targets = {"kill": lambda a: kill_targets(a, stdin), "pkill": pkill_targets,
                           "killall": killall_targets}[program](words[1:])
            except (Unresolved, shell.Unreadable):
                continue
            if targets is not None:
                found.append((shell.show(words), targets))
    return found


def slotfather() -> str | None:
    """$MASTACK_SLOTFATHER or `slotfather` in hooks.json when set (None when it is not executable), else PATH, else
    ~/.local/bin/slotfather, where slotfather's installer puts it."""
    configured = os.environ.get("MASTACK_SLOTFATHER") or hook_io.config().get("slotfather")
    if isinstance(configured, str) and configured:
        path = os.path.expanduser(configured)
        return path if os.access(path, os.X_OK) else None
    found = shutil.which("slotfather")
    fallback = os.path.expanduser("~/.local/bin/slotfather")
    return found or (fallback if os.access(fallback, os.X_OK) else None)


def status(program: str, *args: str) -> dict | None:
    try:
        result = subprocess.run([program, "status", "--json", *args], capture_output=True, text=True,
                                timeout=hook_io.timeout(5))
        data = json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("entries"), list) else None


def started(pids) -> dict[int, str]:
    """Each running pid's start time as `ps -o lstart=` prints it, the form slotfather reports."""
    if not pids:
        return {}
    try:
        output = subprocess.run(["ps", "-o", "pid=,lstart=", "-p", ",".join(map(str, sorted(pids)))],
                                capture_output=True, text=True, timeout=hook_io.timeout(5), env={**os.environ, "LC_ALL": "C"}).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    result = {}
    for line in output.splitlines():
        pid, _, start = line.strip().partition(" ")
        if pid.isdigit():
            result[int(pid)] = " ".join(start.split())
    return result


def carrying(pids) -> set[int]:
    """Those of `pids` whose environment holds a SLOTFATHER_LEASE, read as slotfather reads it (`ps -wwE`)."""
    if not pids:
        return set()
    try:
        output = subprocess.run(["ps", "-wwE", "-o", "pid=,command=", "-p", ",".join(map(str, sorted(pids)))],
                                capture_output=True, text=True, timeout=hook_io.timeout(5), env={**os.environ, "LC_ALL": "C"}).stdout
    except (OSError, subprocess.SubprocessError):
        return set(pids)  # unknown: ask each
    found = set()
    for line in output.splitlines():
        pid, _, rest = line.strip().partition(" ")
        if pid.isdigit() and " SLOTFATHER_LEASE=" in " " + rest:
            found.add(int(pid))
    return found


_table = None


def table() -> dict[int, tuple[int, str]]:
    """pid -> (parent pid, command name), read once."""
    global _table
    if _table is None:
        _table = {}
        try:
            output = subprocess.run(["ps", "-axo", "pid=,ppid=,comm="], capture_output=True, text=True,
                                    timeout=hook_io.timeout(5)).stdout
        except (OSError, subprocess.SubprocessError):
            return _table
        for line in output.splitlines():
            parts = line.split(None, 2)
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                _table[int(parts[0])] = (int(parts[1]), parts[2] if len(parts) > 2 else "")
    return _table


def session_process() -> int | None:
    """The Claude Code process of the session this hook runs for: CLAUDE_PID, else the nearest `claude` ancestor."""
    value = os.environ.get("CLAUDE_PID", "")
    if value.isdigit() and int(value) > 1:
        return int(value)
    processes, pid, seen = table(), os.getppid(), set()
    while pid in processes and pid not in seen and pid > 1:
        seen.add(pid)
        parent, command = processes[pid]
        if os.path.basename(command) == "claude":
            return pid
        pid = parent
    return None


def members(groups) -> set[int]:
    return {pid for group in groups for pid in numbers(run(["pgrep", "-g", str(group)]))} if groups else set()


class Caller:
    def __init__(self, data: dict):
        cwd = data.get("cwd")
        self.cwd = os.path.realpath(cwd) if isinstance(cwd, str) and cwd else None
        self.lease = os.environ.get("SLOTFATHER_LEASE") or None
        self.lane = hook_io.lane_for(self.cwd) if self.cwd else None
        self.session = data.get("session_id") if isinstance(data.get("session_id"), str) else None
        self.worktree = hook_io.worktree_root(self.cwd) if self.cwd else None
        # Subagents share the session's id and process, so only the main thread owns by them.
        self.main = not data.get("agent_id")
        self.root = session_process() if self.main else None

    def descends(self, pid) -> bool:
        """Whether the lease holder `pid` was started under the session's Claude Code process."""
        if not self.root or not isinstance(pid, int):
            return False
        processes, seen = table(), set()
        pid = processes.get(pid, (0, ""))[0]
        while pid in processes and pid not in seen and pid > 1:
            if pid == self.root:
                return True
            seen.add(pid)
            pid = processes[pid][0]
        return pid == self.root

    def owns(self, entry: dict) -> bool:
        meta = entry.get("meta") if isinstance(entry.get("meta"), dict) else {}
        lane, session = meta.get("lane"), meta.get("session")
        if self.lease and entry.get("lease") == self.lease:
            return True
        if lane and lane == self.lane:
            return True
        if self.main and ((session and session == self.session) or self.descends(entry.get("pid"))):
            return True
        if lane or (session and session != self.session):
            return False
        cwd = entry.get("cwd")
        return bool(self.worktree and isinstance(cwd, str) and hook_io.worktree_root(cwd) == self.worktree)


def describe(entry: dict) -> str:
    meta = entry.get("meta") if isinstance(entry.get("meta"), dict) else {}
    named = ", ".join(f"{key} {meta[key]}" for key in ("lane", "ticket", "phase", "kind", "session") if meta.get(key))
    return (f"lease {entry.get('label') or entry.get('id')} ({entry.get('state', 'held')}, {entry.get('count')} slot(s)"
            + (f"; {named}" if named else "; no lane or session named") + ")")


def findings(kills_found, caller: Caller) -> list[str]:
    program = slotfather()
    if program is None or not kills_found:
        return []
    queue = status(program)
    if queue is None or not queue["entries"]:
        return []
    found = []
    for shown, targets in kills_found:
        if targets.everything:
            others = [entry for entry in queue["entries"] if not caller.owns(entry)]
            found += [f"`{shown}` signals every process, so {describe(entry)} too." for entry in others]
            continue
        pids = targets.pids | members(targets.groups)
        if len(pids) > PER_PID_LIMIT:
            # The rest can be in no lease: slotfather places a pid by its tree or by the SLOTFATHER_LEASE it carries.
            trees = {pid for entry in queue["entries"] for pid in entry.get("tree") or []}
            pids &= trees | carrying(pids)
        before = started(pids)
        from concurrent.futures import ThreadPoolExecutor  # only a kill that reaches a lease pays for it
        with ThreadPoolExecutor(max_workers=8) as pool:
            answers = dict(zip(sorted(before), pool.map(lambda pid: status(program, "--pid", str(pid)), sorted(before))))
        for pid, answer in answers.items():
            if answer is None:
                continue
            entries = [entry for entry in answer["entries"] if not caller.owns(entry)]
            if not entries:
                continue
            seen = (answer.get("query") or {}).get("start")
            if seen is None:
                continue  # it ended while slotfather looked
            if " ".join(str(seen).split()) != before[pid]:
                found.append(f"`{shown}`: pid {pid} started at {before[pid]}, slotfather saw one started at {seen}: "
                             "the pid was reused while this guard looked; look again before signalling it.")
                continue
            for entry in entries:
                how = ("its holder" if entry.get("pid") == pid else "in its tree" if entry.get("via") == "tree"
                       else "outside its tree, carrying its SLOTFATHER_LEASE")
                found.append(f"`{shown}` reaches pid {pid}, {how}: {describe(entry)}.")
    return found


def message(found: list[str], override: str | None = None) -> str:
    if override:
        rule = (f"lease-guard: this command signals a process inside another holder's slotfather lease. "
                f"Its LEASE_GUARD_OK reason is {override!r}; only the owner approves it, here.")
        return "\n".join([rule, *(f"- {line}" for line in dict.fromkeys(found))])
    rule = ("lease-guard denied this command: it signals a process inside another holder's slotfather "
            "lease, and the owner's rule is never to kill another holder's lease.")
    safe = ("Safe: leave it to the lane or session that holds it, or wait for it (`slotfather status`); signal only "
            "processes of your own lease. A stuck lease of another lane is the orchestrator's or the owner's call.")
    return "\n".join([rule, *(f"- {line}" for line in dict.fromkeys(found)), safe])


def check(data: dict):
    command = hook_io.command_of(data)
    if command is None or "kill" not in command:
        return None
    global shell
    import unguarded_sequence
    shell = unguarded_sequence
    try:
        parsed = shell.parse(hook_io.strip_heredocs(command))
        # The override is a leading assignment of the first command.
        words = parsed[0][0][0][0][0][1] if parsed and parsed[0][0][0][0][0][0] == "simple" else []
    except (shell.Unreadable, ValueError, IndexError, RecursionError):
        return None
    override = None
    for word in words:
        if not shell.ASSIGNMENT.match(word.raw):
            break
        key, _, value = word.text.partition("=")
        if key == "LEASE_GUARD_OK" and value.strip():
            override = value.strip()
    try:
        found = findings(kills(command), Caller(data))
    except (shell.Unreadable, ValueError, IndexError, RecursionError):
        return None
    if found and override:
        # The prefix is the agent's words; the approval is the owner's, on the permission card.
        hook_io.log("guard.log", f"lease-guard override asked reason={override!r} agent={data.get('agent_id')} "
                                 f"cwd={data.get('cwd')} command={command!r}")
        return hook_io.ask(message(found, override))
    if found:
        return hook_io.deny(message(found))
    return None


if __name__ == "__main__":
    sys.exit(hook_io.run("lease-guard", check))
