"""Shared plumbing for the agent hooks in this directory.

Hooks fail open: a hook that cannot read its input, its configuration or a project file lets the action proceed
rather than trap an agent on a hook bug.

Machine settings come from `$MASTACK_CONFIG/hooks.json` (default `~/.config/mastack/hooks.json`):

    {
      "checkouts": ["~/app", "~/lib"],        shared main checkouts: push-by-name and shared-checkout apply
      "state_dir": "~/some/state",            where guard.log goes (default $XDG_STATE_HOME/mastack)
      "lane_records": "~/some/state/lanes",   the lane tool's records, for the lease guard (default: none)
      "mutating_steps": ["tools/deploy.sh"],  extra steps for the unguarded-sequence guard, on every project
      "slotfather": "~/bin/slotfather"        the slotfather the lease guard asks (default: PATH, ~/.local/bin)
    }

`MASTACK_HOOK_REPOS` (colon-separated), `MASTACK_HOOK_STATE`, `MASTACK_LANE_RECORDS` and `MASTACK_SLOTFATHER` replace
the matching setting. A project adds its own steps in `docs/agents/hooks.json` (see `project_config`).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

# A heredoc operator and its delimiter: <<EOF, <<-'EOF', << "EOF"; the caller rules out the here-string <<<.
HEREDOC = re.compile(r"<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
PROJECT_FILE = os.path.join("docs", "agents", "hooks.json")


def strip_heredocs(command: str) -> str:
    """The command without heredoc bodies: their text is data for the receiving command, not shell.

    Only an unquoted, uncommented `<<` starts a heredoc, so `echo "<<EOF"` cannot hide the lines after it; inside
    `"$( ... )"` the text is unquoted again, as in `git commit -m "$(cat <<'EOF' ...)"`."""
    out: list[str] = []
    pending: list[tuple[bool, str]] = []
    stack: list[str] = []  # open contexts: ' and " quote, $( and ( do not
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        context = stack[-1] if stack else ""
        if context == "'":
            if c == "'":
                stack.pop()
            out.append(c)
            i += 1
        elif c == "\\":
            out.append(command[i:i + 2])
            i += 2
        elif command.startswith("$(", i) and context in ('"', "", "$(", "("):
            stack.append("$(")
            out.append("$(")
            i += 2
        elif context == '"':
            if c == '"':
                stack.pop()
            out.append(c)
            i += 1
        elif c in "'\"(":
            stack.append(c)
            out.append(c)
            i += 1
        elif c == ")":
            if stack:
                stack.pop()
            out.append(c)
            i += 1
        elif c == "#" and (i == 0 or command[i - 1] in " \t\n;&|("):
            end = command.find("\n", i)
            end = n if end < 0 else end
            out.append(command[i:end])
            i = end
        elif command.startswith("<<", i) and not command.startswith("<<<", i) and command[i - 1:i] != "<" \
                and (match := HEREDOC.match(command, i)):
            pending.append((match.group(1) == "-", match.group(3)))
            out.append(match.group(0))
            i = match.end()
        elif c == "\n" and pending:
            out.append(c)
            i += 1
            while pending and i < n:  # skip each body through its delimiter line
                end = command.find("\n", i)
                line = command[i:n if end < 0 else end]
                i = n if end < 0 else end + 1
                dash, tag = pending[0]
                if (line.lstrip("\t") if dash else line) == tag:
                    pending.pop(0)
        else:
            out.append(c)
            i += 1
    return "".join(out)


# ---- configuration ------------------------------------------------------------------------------------------------

_config: dict | None = None


def read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def config() -> dict:
    """The machine settings, read once; {} when the file is missing or unreadable."""
    global _config
    if _config is None:
        directory = os.environ.get("MASTACK_CONFIG") or os.path.join(Path.home(), ".config", "mastack")
        _config = read_json(os.path.join(os.path.expanduser(directory), "hooks.json"))
    return _config


def strings(value) -> list[str]:
    return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []


def repos() -> list[str]:
    """The shared main checkouts the git guard protects; their .claude/worktrees hold lanes."""
    configured = os.environ.get("MASTACK_HOOK_REPOS")
    names = configured.split(":") if configured else strings(config().get("checkouts"))
    return [os.path.realpath(os.path.expanduser(name)) for name in names if name]


def state_dir() -> Path:
    configured = os.environ.get("MASTACK_HOOK_STATE") or config().get("state_dir")
    if isinstance(configured, str) and configured:
        return Path(os.path.expanduser(configured))
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(Path.home(), ".local", "state")
    return Path(base) / "mastack"


def lane_records() -> str | None:
    configured = os.environ.get("MASTACK_LANE_RECORDS") or config().get("lane_records")
    return os.path.expanduser(configured) if isinstance(configured, str) and configured else None


def main_checkout(root: str) -> str | None:
    """The main checkout of the linked worktree at root, read from its .git file without running git."""
    try:
        with open(os.path.join(root, ".git"), encoding="utf-8") as handle:
            line = handle.readline().strip()
    except OSError:
        return None
    if not line.startswith("gitdir:"):
        return None
    gitdir = os.path.join(root, line.split(":", 1)[1].strip())
    common = gitdir
    try:
        with open(os.path.join(gitdir, "commondir"), encoding="utf-8") as handle:
            common = os.path.join(gitdir, handle.readline().strip())
    except OSError:
        pass
    common = os.path.realpath(common)
    return os.path.dirname(common) if os.path.basename(common) == ".git" else None


def project_config(cwd: str | None) -> dict:
    """`docs/agents/hooks.json` of the repository the session works in: its worktree's copy, else the main
    checkout's (a lane branch cut before the file existed still gets the project's list). {} when none."""
    if not cwd:
        return {}
    root = worktree_root(cwd)
    if root is None:
        return {}
    data = read_json(os.path.join(root, PROJECT_FILE))
    if not data and os.path.isfile(os.path.join(root, ".git")):
        main = main_checkout(root)
        if main:
            data = read_json(os.path.join(main, PROJECT_FILE))
    return data


# ---- time budget --------------------------------------------------------------------------------------------------

class OutOfTime(TimeoutError):
    """The hook's time budget is spent: the caller treats it like a failed subprocess and fails open."""


_deadline: float | None = None


def set_budget(seconds: float) -> None:
    """Give every later subprocess a share of `seconds` from now, so the hook answers before its own timeout."""
    global _deadline
    _deadline = time.monotonic() + seconds


def remaining() -> float | None:
    return None if _deadline is None else _deadline - time.monotonic()


def timeout(wanted: float) -> float:
    """A subprocess timeout that fits the budget: `wanted`, or less; OutOfTime once nothing is left."""
    left = remaining()
    if left is None:
        return wanted
    if left <= 0.05:
        raise OutOfTime
    return min(wanted, left)


# ---- input and output ---------------------------------------------------------------------------------------------

def log(name: str, message: str) -> None:
    try:
        directory = state_dir()
        directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with open(directory / name, "a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {message}\n")
    except OSError:
        pass


def read_input() -> dict:
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def command_of(data: dict) -> str | None:
    command = (data.get("tool_input") or {}).get("command") if isinstance(data.get("tool_input"), dict) else None
    return command if isinstance(command, str) else None


def deny(reason: str) -> tuple[str, str]:
    """A PreToolUse deny: the reason is shown to the model as the tool error."""
    return ("deny", reason)


def ask(reason: str) -> tuple[str, str]:
    """A PreToolUse ask: the permission card shows the reason, and the owner decides."""
    return ("ask", reason)


def emit(decision: tuple[str, str] | None) -> None:
    if decision:
        json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision[0],
                                          "permissionDecisionReason": decision[1]}}, sys.stdout)


def run(name: str, check) -> int:
    """Run one check as a hook of its own: JSON on stdin, decision on stdout, exit 0 even when the check fails."""
    try:
        emit(check(read_input()))
    except Exception as error:  # noqa: BLE001 - fail open
        log("guard.log", f"{name} error {error!r}")
    return 0


# ---- worktrees and lanes ------------------------------------------------------------------------------------------

def worktree_root(path: str) -> str | None:
    """The Git worktree `path` is in (the first directory upward holding .git), or None."""
    current = os.path.realpath(path)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def lane_for(path: str) -> str | None:
    """The id of the lane whose worktree holds `path`, as the lane tool's records name it (the `lane` a lease's
    metadata carries). A review-fix lane takes over its landed lane's worktree, so a record still working in it
    wins."""
    records = lane_records()
    root = worktree_root(path)
    if root is None or records is None:
        return None
    found = []
    try:
        names = sorted(os.listdir(records))
    except OSError:
        return None
    for name in names:
        if not re.fullmatch(r"[^.]+\.json", name):
            continue
        try:
            with open(os.path.join(records, name), encoding="utf-8") as handle:
                record = json.load(handle)
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and isinstance(record.get("worktree"), str) \
                and os.path.realpath(record["worktree"]) == root:
            found.append(record)
    if not found:
        return None
    record = max(found, key=lambda r: (r.get("status") not in ("done", "released"), str(r.get("created") or "")))
    return str(record.get("id") or "") or None
