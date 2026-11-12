#!/usr/bin/env python3
"""Register mastack's hooks in a Claude Code settings file; bin/install runs it.

    hooks/register.py --settings FILE [--config DIR] [--dry-run] [--uninstall] [--from-worktree]

Install adds one PreToolUse group (matcher Bash) that runs hooks/bash_guard.py of this checkout, through `sh` so a
missing file lets every command through instead of blocking it. In Bash groups only, it removes the handlers that
one replaces: the separate checks of an earlier agent-hooks directory (git-guard.py, zsh-word-split.py,
unguarded-sequence.py, lease-guard.py), ~/.claude/hooks/macos-shell-pitfalls.sh, and the mastack commands an
earlier install recorded in DIR/hooks-installed.json. A group left without handlers is dropped; every other entry
stays as it is. Uninstall removes only the recorded mastack commands and this checkout's.

For each lifecycle event the machine settings list under `lifecycle` (SubagentStart, SubagentStop, Stop,
SessionStart, SessionEnd; hooks/lifecycle.py), install adds one group that runs hooks/lifecycle.py EVENT, and removes
that group from the events no longer listed. `lifecycle.PreToolUse` needs no group: bash_guard.py runs it.

Install refuses (exit 1) when DIR/hooks.json, the machine settings the checks read, is missing or unreadable:
without it git-guard protects no checkout and the lease guard knows no lane (hooks/hooks.example.json shows the
fields). It refuses to register a linked worktree, whose path disappears with it, unless --from-worktree.

Before writing it copies FILE to FILE.mastack-backup-<time>; --dry-run writes nothing and prints the diff. A
missing FILE is created; one that is not a JSON object, or whose hooks are malformed, is refused and left alone. The
write goes to the file a symlink points at, and is retried when Claude Code changed the file meanwhile.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shlex
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "hooks" / "bash_guard.py"
LIFECYCLE = ROOT / "hooks" / "lifecycle.py"
LIFECYCLE_EVENTS = ("SubagentStart", "SubagentStop", "Stop", "SessionStart", "SessionEnd")  # lifecycle.EVENTS
LIFECYCLE_TIMEOUT = 30  # lifecycle.HOOK_TIMEOUT
REPLACED = re.compile(r"agent-hooks/(git-guard|zsh-word-split|unguarded-sequence|lease-guard)\.py[\"']?\s*$"
                      r"|\.claude/hooks/macos-shell-pitfalls\.sh[\"']?\s*$")
TIMEOUT = 10  # bash_guard.HOOK_TIMEOUT: its checks answer within bash_guard.BUDGET
RECORD = "hooks-installed.json"
ATTEMPTS = 3


class Refused(Exception):
    pass


def tilde(path) -> str:
    path, home = str(path), str(Path.home())
    return "~" + path[len(home):] if path == home or path.startswith(home + "/") else path


def command() -> str:
    """Runs the dispatcher when its file exists and passes the command when it does not (a removed checkout)."""
    return f"sh -c '[ -f \"$0\" ] || exit 0; exec python3 \"$0\"' {shlex.quote(str(GUARD))}"


def handler() -> dict:
    return {"type": "command", "command": command(), "timeout": TIMEOUT}


def lifecycle_command(event: str) -> str:
    """Runs the lifecycle dispatcher for one event, and nothing when its file is gone."""
    return (f"sh -c '[ -f \"$0\" ] || exit 0; exec python3 \"$0\" \"$1\"' {shlex.quote(str(LIFECYCLE))} "
            f"{shlex.quote(event)}")


def lifecycle_handler(event: str) -> dict:
    return {"type": "command", "command": lifecycle_command(event), "timeout": LIFECYCLE_TIMEOUT}


def lifecycle_events(config: Path) -> list[str]:
    """The lifecycle events the machine settings list commands for."""
    try:
        data = json.loads((config / "hooks.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    lifecycle = data.get("lifecycle") if isinstance(data, dict) else None
    if not isinstance(lifecycle, dict):
        return []
    return [event for event in LIFECYCLE_EVENTS if isinstance(lifecycle.get(event), list) and lifecycle[event]]


def lifecycle_groups(hooks: dict, event: str, want: bool, ours: set[str], report: list[str]) -> None:
    """Keep exactly one group running the dispatcher for `event` when wanted, none otherwise; others stay."""
    groups = hooks.get(event, [])
    if not isinstance(groups, list):
        raise Refused(f"`hooks.{event}` is not a list")
    mine, kept, present = lifecycle_handler(event), [], False
    for group in groups:
        entries = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(entries, list):
            kept.append(group)
            continue
        remaining = []
        for entry in entries:
            text = entry.get("command") if isinstance(entry, dict) else None
            if not (isinstance(text, str) and text in ours):
                remaining.append(entry)
            elif want and not present and entry == mine and len(entries) == 1:
                present = True
                remaining.append(entry)
            else:
                report.append(f"remove {event}: {tilde(text)}")
        if remaining:
            kept.append(group if len(remaining) == len(entries) else {**group, "hooks": remaining})
    if want and not present:
        kept.append({"hooks": [mine]})
        report.append(f"add    {event}: {tilde(lifecycle_command(event))}")
    if kept:
        hooks[event] = kept
    else:
        hooks.pop(event, None)


def recorded(config: Path) -> list[str]:
    try:
        data = json.loads((config / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    commands = data.get("commands") if isinstance(data, dict) else None
    return [c for c in commands if isinstance(c, str)] if isinstance(commands, list) else []


def record(config: Path, commands: list[str]) -> None:
    config.mkdir(parents=True, exist_ok=True)
    (config / RECORD).write_text(json.dumps({"commands": commands}, indent=2) + "\n", encoding="utf-8")


def updated(settings: dict, uninstall: bool, ours: set[str], report: list[str], events=()) -> dict:
    if not isinstance(settings, dict):
        raise Refused("not a JSON object")
    result = json.loads(json.dumps(settings))
    hooks = result.get("hooks", {})
    if not isinstance(hooks, dict):
        raise Refused("`hooks` is not an object")
    groups = hooks.get("PreToolUse", [])
    if not isinstance(groups, list):
        raise Refused("`hooks.PreToolUse` is not a list")
    kept, position = [], None
    for group in groups:
        entries = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(entries, list) or group.get("matcher") != "Bash":
            kept.append(group)
            continue
        remaining = []
        for entry in entries:
            text = entry.get("command") if isinstance(entry, dict) else None
            mine = isinstance(text, str) and text in ours
            old = isinstance(text, str) and not uninstall and REPLACED.search(text)
            if mine or old:
                if uninstall or entry != handler() or len(entries) != 1:
                    report.append(f"remove PreToolUse Bash: {tilde(text)}")
                position = len(kept) if position is None else position
            else:
                remaining.append(entry)
        if remaining:
            kept.append({**group, "hooks": remaining} if len(remaining) != len(entries) else group)
    if not uninstall:
        mine = {"matcher": "Bash", "hooks": [handler()]}
        kept.insert(len(kept) if position is None else position, mine)
        if mine not in groups:
            report.append(f"add    PreToolUse Bash: {tilde(command())}")
    for event in LIFECYCLE_EVENTS:
        if event in hooks or event in events:
            lifecycle_groups(hooks, event, not uninstall and event in events, ours, report)
    if kept:
        hooks["PreToolUse"] = kept
        result["hooks"] = hooks
    else:
        hooks.pop("PreToolUse", None)
        if hooks:
            result["hooks"] = hooks
        else:
            result.pop("hooks", None)
    return result


def render(settings: dict, ascii_only: bool) -> str:
    return json.dumps(settings, indent=2, ensure_ascii=ascii_only) + "\n"


def preflight(args) -> None:
    if args.uninstall:
        return
    if (ROOT / ".git").is_file() and not args.from_worktree:
        raise Refused(f"{tilde(ROOT)} is a linked worktree, whose path disappears with it; install from the main "
                      "checkout (or pass --from-worktree to register this path anyway)")
    machine = args.config / "hooks.json"
    try:
        data = json.loads(machine.read_text(encoding="utf-8"))
    except OSError:
        raise Refused(f"no {tilde(machine)}: without it git-guard protects no checkout and the lease guard knows "
                      f"no lane. Copy {tilde(ROOT / 'hooks' / 'hooks.example.json')} there and fill it in, "
                      "or write {} to run without those") from None
    except ValueError as error:
        raise Refused(f"{tilde(machine)} is not JSON: {error}") from None
    if not isinstance(data, dict):
        raise Refused(f"{tilde(machine)} is not a JSON object")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--settings", required=True, type=Path, help="the Claude Code settings file")
    parser.add_argument("--config", type=Path, default=Path(os.environ.get("MASTACK_CONFIG") or
                                                            Path.home() / ".config" / "mastack"))
    parser.add_argument("--dry-run", action="store_true", help="print the diff, change nothing")
    parser.add_argument("--uninstall", action="store_true", help="remove mastack's handlers only")
    parser.add_argument("--from-worktree", action="store_true", help="register a linked worktree's path")
    args = parser.parse_args()
    args.config = args.config.expanduser()

    path = args.settings.expanduser()
    print(tilde(path))
    target = path.resolve()  # a symlinked settings file stays a symlink
    events = lifecycle_events(args.config)
    ours = set(recorded(args.config)) | {command()} | {lifecycle_command(event) for event in LIFECYCLE_EVENTS}
    backup = None
    try:
        preflight(args)
        for _ in range(ATTEMPTS):
            before = target.read_text(encoding="utf-8") if target.exists() else ""
            try:
                settings = json.loads(before) if before.strip() else {}
            except ValueError as error:
                raise Refused(f"not JSON: {error}") from None
            report: list[str] = []
            after_settings = updated(settings, args.uninstall, ours, report, events)
            if after_settings == settings:
                print("  ok     hooks" if not args.uninstall else "  ok     no mastack hook")
                break
            for line in report:
                print(f"  {line}")
            after = render(after_settings, before.isascii())
            if args.dry_run:
                sys.stdout.writelines(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                                           tilde(path), tilde(path) + " (after)"))
                return 0
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and backup is None:
                backup = target.with_name(f"{target.name}.mastack-backup-{time.strftime('%Y%m%d-%H%M%S')}")
                backup.write_text(before, encoding="utf-8")
                shutil.copymode(target, backup)
                print(f"  backup {tilde(backup)}")
            temporary = target.with_name(f".{target.name}.mastack-{os.getpid()}")
            temporary.write_text(after, encoding="utf-8")
            if target.exists():
                shutil.copymode(target, temporary)
            current = target.read_text(encoding="utf-8") if target.exists() else ""
            if current != before:  # written meanwhile, by Claude Code or another install: start over
                temporary.unlink()
                print("  retry  the file changed while this ran")
                continue
            os.replace(temporary, target)
            break
        else:
            raise Refused(f"the file kept changing; tried {ATTEMPTS} times, nothing changed")
    except (OSError, Refused) as error:
        print(f"  refuse {error}", file=sys.stderr)
        return 1
    if not args.dry_run:
        record(args.config, [] if args.uninstall else [command()] + [lifecycle_command(e) for e in events])
    return 0


if __name__ == "__main__":
    sys.exit(main())
