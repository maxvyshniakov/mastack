#!/usr/bin/env python3
"""Docker Desktop guard, a Claude Code PreToolUse[Bash] check: refresh services, never the whole Docker Desktop.

Quitting, killing or restarting Docker Desktop to refresh one service stops every container on the machine, other
sessions' included, and a Docker Desktop opened in front is pulled onto the active Space, over the owner's work.

Denies, on macOS's Docker Desktop:
  - `osascript` that quits the app (`quit app "Docker"`, `tell application "Docker Desktop" to quit`, by bundle id
    `com.docker.docker`, or JXA `Application("Docker").quit()`);
  - `killall` of its processes by name (`Docker`, `Docker Desktop`, `com.docker.*`; with -m, as a regex);
  - `pkill` whose pattern matches one of its process names, or with -f one of its command lines (`pkill -f docker`
    reaches com.docker.backend);
  - `kill` of a pid found by name: `kill $(pgrep Docker)`, `kill $(ps ax | grep "Docker Desktop" | ...)`,
    `pgrep -f com.docker | xargs kill`;
  - `docker desktop stop` and `docker desktop restart`;
  - `open` of the app (`-a Docker`, `-a "Docker Desktop"`, `-b com.docker.docker`, `Docker.app`) without both -g
    and -j: `open -gja Docker` starts it hidden and in the background and passes.
These are found in chains, pipes, compound commands, command substitutions and `sh|bash|zsh -c` scripts. Ordinary
docker CLI use passes (`docker compose restart`, `docker restart CONTAINER`, `docker info`), as do OrbStack's `orb`
and `orbctl`, signal 0, `killall -s` and `kill -l` (they only look). A pid or pattern held in a variable is not
seen: misses are preferred to false positives. Read like the unguarded-sequence guard reads the shell; a command it
cannot parse passes.
"""
from __future__ import annotations

import os
import re
import sys

import hook_io

SHELLS = {"sh", "bash", "zsh"}
# Docker Desktop's process names, and the command lines `pgrep -f` and `ps ax` see for them.
NAMES = ("Docker", "Docker Desktop", "com.docker.backend", "com.docker.build", "com.docker.virtualization",
         "com.docker.vmnetd", "com.docker.hyperkit", "com.docker.dev-envs")
APP = "/Applications/Docker.app/Contents/MacOS/"
LINES = (APP + "Docker Desktop.app/Contents/MacOS/Docker Desktop", APP + "com.docker.backend",
         APP + "com.docker.build", APP + "com.docker.virtualization --kernel", APP + "com.docker.hyperkit",
         "/Library/PrivilegedHelperTools/com.docker.vmnetd")
BUNDLE = "com.docker.docker"
APP_NAMES = {"docker", "docker desktop"}

SIGNAL = re.compile(r"-(\d+|[A-Z][A-Z0-9+-]*|SIG[A-Za-z0-9+-]+)")
PGREP_VALUE = {"-F", "-G", "-g", "-P", "-t", "-U", "-u", "-s", "-J", "-d", "-M", "-N", "--signal"}
KILLALL_VALUE = {"-u", "-t", "-c"}
GREP_VALUE = {"-A", "-B", "-C", "-m", "-f", "--context", "--max-count", "--file", "--label", "--color",
              "--colour", "-d", "-D", "--include", "--exclude"}
DOCKER_VALUE = {"--context", "-c", "--config", "-H", "--host", "-l", "--log-level", "--tlscacert", "--tlscert",
                "--tlskey"}
OPEN_VALUE = {"-a", "-b", "-u", "--env", "--stdin", "--stdout", "--stderr", "--arch", "-s"}

QUIT = re.compile(r"\bquit\b", re.I)
APP_REF = re.compile(r"\bapp(lication)?\s+(id\s+)?[\"'](docker( desktop)?|com\.docker\.docker)[\"']", re.I)
JXA_QUIT = re.compile(r"Application\(\s*[\"'](docker( desktop)?|com\.docker\.docker)[\"']\s*\)\s*\.\s*quit\s*\(",
                      re.I)


def name_of(words) -> str:
    return (words[0].literal or "").rsplit("/", 1)[-1] if words else ""


def shell_script(own):
    """The script of `sh|bash|zsh -c SCRIPT` (also `bash -lc`), or None."""
    if name_of(own) not in SHELLS:
        return None
    literals = [w.literal or "" for w in own[1:]]
    at = next((i for i, w in enumerate(literals) if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", w)), None)
    if at is None:
        return None
    script = next((own[1 + i] for i in range(at + 1, len(literals)) if not literals[i].startswith("-")), None)
    return script.literal if script is not None else None


def pipelines(shell, text: str, depth: int = 0):
    """Every pipeline of a command as a list of its stages' own words (a compound stage contributes its own
    pipelines instead), through compound commands, command substitutions and `sh -c` scripts."""
    if depth > 8:
        return
    yield from walk(shell, shell.parse(hook_io.strip_heredocs(text)), depth)


def walk(shell, lst, depth):
    for and_or, _ in lst:
        for pipeline, _ in and_or:
            stages = []
            for command in pipeline:
                yield from compound(shell, command, depth, stages)
            if stages:
                yield stages


def compound(shell, command, depth, stages):
    kind = command[0]
    if kind == "simple":
        own = shell.unwrap(command[1])
        for word in command[1]:
            for sub in word.subs:
                yield from pipelines(shell, sub, depth + 1)
        script = shell_script(own)
        if script is not None:
            yield from pipelines(shell, script, depth + 1)
        elif own:
            stages.append(own)
    elif kind in ("group", "subshell", "function"):
        yield from walk(shell, command[1], depth)
    elif kind == "if":
        for condition, body in command[1]:
            yield from walk(shell, condition, depth)
            yield from walk(shell, body, depth)
        yield from walk(shell, command[2] or [], depth)
    elif kind == "loop":
        yield from walk(shell, command[1], depth)
        yield from walk(shell, command[2], depth)
    elif kind == "case":
        for body in command[1]:
            yield from walk(shell, body, depth)


def search(pattern: str, texts, flags=0, whole=False) -> bool:
    try:
        compiled = re.compile(pattern, flags)
        return any((compiled.fullmatch if whole else compiled.search)(text) for text in texts)
    except (re.error, RecursionError):
        return False


def pgrep_reaches(own) -> bool:
    """A `pgrep` or `pkill` whose literal pattern matches a Docker Desktop process (name, or with -f its command
    line). -v (inverted) is not judged."""
    args = own[1:]
    if args and SIGNAL.fullmatch(args[0].literal or ""):
        if name_of(own) == "pkill" and args[0].literal in ("-0", "-SIGZERO"):
            return False
        args = args[1:]
    full, flags, whole, found, index = False, 0, False, [], 0
    while index < len(args):
        value = args[index].literal
        if value is not None and value in PGREP_VALUE:
            index += 2
            continue
        if value is not None and re.fullmatch(r"-[A-Za-z]+", value):
            if "v" in value:
                return False
            full = full or "f" in value
            flags |= re.I if "i" in value else 0
            whole = whole or "x" in value
        elif value is not None and value != "--":
            found.append(value)
        index += 1
    texts = LINES + NAMES if full else NAMES
    return any(search(pattern, texts, flags, whole) for pattern in found)


def grep_reaches(own) -> bool:
    """A grep or rg whose literal pattern matches a Docker Desktop line of `ps ax`; -v is not judged."""
    args, patterns, flags, fixed, index, explicit = own[1:], [], 0, False, 0, False
    while index < len(args):
        value = args[index].literal
        if value is None:
            index += 1
            continue
        if value in ("-e", "--regexp") and index + 1 < len(args):
            if args[index + 1].literal is not None:
                patterns.append(args[index + 1].literal)
            explicit = True
            index += 2
            continue
        if value in GREP_VALUE:
            index += 2
            continue
        if value.startswith("--"):
            if value in ("--invert-match",):
                return False
            flags |= re.I if value == "--ignore-case" else 0
            fixed = fixed or value == "--fixed-strings"
        elif value.startswith("-") and len(value) > 1:
            if "v" in value:
                return False
            flags |= re.I if "i" in value else 0
            fixed = fixed or "F" in value
        elif not explicit:
            patterns.append(value)
            explicit = True
        index += 1
    return any(search(re.escape(p) if fixed else p, LINES + NAMES, flags) for p in patterns)


def finds_docker(stages) -> bool:
    for own in stages:
        name = name_of(own)
        if name in ("pgrep", "pkill") and pgrep_reaches(own):
            return True
        if name in ("grep", "egrep", "fgrep", "rg") and grep_reaches(own):
            return True
    return False


def kill_looks_only(own) -> bool:
    literals = [w.literal for w in own[1:]]
    return bool(literals) and (literals[0] in ("-0", "-l", "-L") or literals[:2] == ["-s", "0"])


def killall_reaches(own) -> bool:
    args, regex, targets, index = own[1:], False, [], 0
    while index < len(args):
        value = args[index].literal
        if value is None:
            index += 1
            continue
        if value in KILLALL_VALUE and index + 1 < len(args):
            if value == "-c" and args[index + 1].literal is not None:
                targets.append(args[index + 1].literal)
            index += 2
            continue
        if value in ("-s", "-l", "-0", "-help", "-h", "-?"):
            return False
        if value == "-m":
            regex = True
        elif not value.startswith("-"):
            targets.append(value)
        index += 1
    for target in targets:
        if regex and search(target, NAMES):
            return True
        if not regex and (target in NAMES or target.startswith("com.docker.")):
            return True
    return False


def osascript_quits(own) -> bool:
    args, scripts, index = own[1:], [], 0
    while index < len(args):
        value = args[index].literal
        if value == "-e" and index + 1 < len(args):
            scripts.append(args[index + 1].literal or "")
            index += 2
            continue
        index += 1
    text = "\n".join(scripts)
    return bool((QUIT.search(text) and APP_REF.search(text)) or JXA_QUIT.search(text))


def docker_desktop_stops(own) -> str | None:
    args, index, rest = own[1:], 0, []
    while index < len(args):
        value = args[index].literal
        if value is None:
            return None
        if value in DOCKER_VALUE:
            index += 2
            continue
        if not value.startswith("-"):
            rest = [w.literal for w in args[index:]]
            break
        index += 1
    if not rest or rest[0] != "desktop":
        return None
    verb = next((w for w in rest[1:] if w is None or not w.startswith("-")), None)
    return verb if verb in ("stop", "restart") else None


def opens_in_front(own) -> bool:
    """An `open` of Docker Desktop without both -g (background) and -j (hidden)."""
    args, flags, docker, index = own[1:], set(), False, 0
    while index < len(args):
        value = args[index].literal
        if value is None:
            index += 1
            continue
        if value == "--args":
            break
        if value in ("--background", "--hide"):
            flags.add("g" if value == "--background" else "j")
            index += 1
            continue
        if value in OPEN_VALUE or (re.fullmatch(r"-[A-Za-z]+", value) and value[-1] in "ab"):
            option = value[-1] if not value.startswith("--") else value
            flags.update(value[1:-1] if not value.startswith("--") else "")
            target = args[index + 1].literal if index + 1 < len(args) else None
            if target is not None:
                app = os.path.basename(target.rstrip("/"))
                app = app[:-4] if app.lower().endswith(".app") else app
                if (option == "a" and app.lower() in APP_NAMES) or (option == "b" and target.lower() == BUNDLE):
                    docker = True
            index += 2
            continue
        if re.fullmatch(r"-[A-Za-z]+", value):
            flags.update(value[1:])
        elif not value.startswith("-") and os.path.basename(value.rstrip("/")).lower() == "docker.app":
            docker = True
        index += 1
    return docker and not {"g", "j"} <= flags


def findings(shell, command: str):
    for stages in pipelines(shell, command):
        for at, own in enumerate(stages):
            name = name_of(own)
            shown = shell.show(own)
            if name == "osascript" and osascript_quits(own):
                yield shown, "quits Docker Desktop"
            elif name == "killall" and killall_reaches(own):
                yield shown, "kills Docker Desktop's processes by name"
            elif name == "pkill" and pgrep_reaches(own):
                yield shown, "matches Docker Desktop's processes"
            elif name == "kill" and not kill_looks_only(own) and any(
                    finds_docker(sub) for word in own[1:] for s in word.subs for sub in pipelines(shell, s)):
                yield shown, "kills a Docker Desktop process found by name"
            elif name == "xargs" and any(name_of(own[i:]) == "kill" for i in range(1, len(own))) \
                    and finds_docker(stages[:at]):
                yield shell.show([w for stage in stages[:at + 1] for w in stage]), \
                    "kills a Docker Desktop process found by name"
            elif name == "docker":
                verb = docker_desktop_stops(own)
                if verb:
                    yield shown, f"{'restarts' if verb == 'restart' else 'stops'} Docker Desktop"
            elif name == "open" and opens_in_front(own):
                yield shown, "opens Docker Desktop in front, onto the active Space"


def check(data: dict):
    command = hook_io.command_of(data)
    if command is None or ("docker" not in command and "Dock" not in command):
        return None
    import unguarded_sequence as shell
    try:
        found = list(dict.fromkeys(findings(shell, command)))
    except (shell.Unreadable, ValueError, IndexError, StopIteration, RecursionError):
        return None
    if not found:
        return None
    lines = [f"- `{shown}` {why}." for shown, why in found]
    return hook_io.deny(
        "docker-desktop denied this command: quitting, killing or restarting Docker Desktop to refresh services "
        "stops every container on the machine, other sessions' included, and opening it in front pulls it onto the "
        "active Space.\n" + "\n".join(lines) + "\n"
        "Instead: restart only what needs it: `docker compose restart [service]`, "
        "`docker compose up -d --force-recreate [service]` or `docker restart <container>`. If the Docker daemon "
        "is not running, check `docker info` first, then start Docker Desktop hidden: `open -gja Docker`.")


if __name__ == "__main__":
    sys.exit(hook_io.run("docker-desktop", check))
