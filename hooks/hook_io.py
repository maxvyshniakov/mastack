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
from typing import NamedTuple

def strip_heredocs(command: str) -> str:
    """Re-exported from `shell` while `git_guard` and `zsh_word_split` still call `hook_io.strip_heredocs`."""
    if "<<" not in command:
        return command
    import shell
    return shell.strip_heredocs(command)

PROJECT_FILE = os.path.join("docs", "agents", "hooks.json")


# ---- configuration ------------------------------------------------------------------------------------------------

_config: dict | None = None


def read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def config_dir(env=None) -> Path:
    """The machine settings directory: `$MASTACK_CONFIG`, else `~/.config/mastack`."""
    env = os.environ if env is None else env
    return Path(env.get("MASTACK_CONFIG") or Path.home() / ".config" / "mastack").expanduser()


def config() -> dict:
    """The machine settings, read once; {} when the file is missing or unreadable."""
    global _config
    if _config is None:
        _config = read_json(str(config_dir() / "hooks.json"))
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


class Answer(NamedTuple):
    """A PreToolUse answer that rewrites the tool's input (a lifecycle rewriter's, hooks/lifecycle.py), with the
    checks' decision when there is one; without it Claude Code's own permission flow judges the rewritten input."""
    decision: tuple[str, str] | None
    updated_input: dict


# Where a hook's `ask` was shown to reach a person or be refused, never auto-approved.
CARD_ENTRYPOINTS = {"t3-code"}
CARD_MODES = {"default", "acceptEdits", "bypassPermissions"}


def card_reaches_owner(data: dict) -> bool:
    """Whether a PreToolUse `ask` reaches a person here, never an automatic approval or a subagent no one watches."""
    if "turn_id" in data or data.get("agent_id"):  # Codex rejects `ask`; a subagent's card is not the owner's
        return False
    return (os.environ.get("CLAUDE_CODE_ENTRYPOINT") in CARD_ENTRYPOINTS
            and data.get("permission_mode") in CARD_MODES)


def emit(decision: tuple[str, str] | Answer | None) -> None:
    if isinstance(decision, Answer):
        output: dict = {"hookEventName": "PreToolUse", "updatedInput": decision.updated_input}
        if decision.decision:
            output.update(permissionDecision=decision.decision[0], permissionDecisionReason=decision.decision[1])
        json.dump({"hookSpecificOutput": output}, sys.stdout)
    elif decision:
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
