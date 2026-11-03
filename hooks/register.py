#!/usr/bin/env python3
"""Register mastack's Bash hook in a Claude Code settings file; bin/install runs it.

    hooks/register.py --settings FILE [--dry-run] [--uninstall]

Install adds one PreToolUse group (matcher Bash) that runs hooks/bash_guard.py, and removes the handlers it
replaces: the separate checks from an earlier agent-hooks directory (git-guard.py, zsh-word-split.py,
unguarded-sequence.py, lease-guard.py) and ~/.claude/hooks/macos-shell-pitfalls.sh, plus a bash_guard.py entry of
another checkout. A group left without handlers is dropped; every other entry stays as it is. Uninstall removes
only mastack's handler. Before writing it copies FILE to FILE.mastack-backup-<time>; --dry-run writes nothing and
prints the diff. A missing FILE is created; one that is not a JSON object is refused (exit 1) and left alone.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OURS = re.compile(r"/hooks/bash_guard\.py[\"']?\s*$")
REPLACED = re.compile(r"agent-hooks/(git-guard|zsh-word-split|unguarded-sequence|lease-guard)\.py[\"']?\s*$"
                      r"|\.claude/hooks/macos-shell-pitfalls\.sh[\"']?\s*$")
TIMEOUT = 10  # the lease guard asks slotfather about each pid it reaches; the other checks take milliseconds


def tilde(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home):] if path == home or path.startswith(home + "/") else path


def handler() -> dict:
    return {"type": "command", "command": f"python3 {ROOT}/hooks/bash_guard.py", "timeout": TIMEOUT}


def updated(settings: dict, uninstall: bool, report: list[str]) -> dict:
    result = json.loads(json.dumps(settings))
    hooks = result.setdefault("hooks", {}) if not uninstall else result.get("hooks", {})
    groups = hooks.get("PreToolUse", []) if isinstance(hooks, dict) else []
    if not isinstance(groups, list):
        raise ValueError("hooks.PreToolUse is not a list")
    kept, position = [], None
    for group in groups:
        entries = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(entries, list):
            kept.append(group)
            continue
        remaining = []
        for entry in entries:
            command = entry.get("command") if isinstance(entry, dict) else None
            ours = isinstance(command, str) and OURS.search(command)
            old = isinstance(command, str) and not uninstall and REPLACED.search(command)
            if ours or old:
                if not (ours and not uninstall and entry == handler() and group.get("matcher") == "Bash"):
                    report.append(f"remove PreToolUse {group.get('matcher', '*')}: {tilde(command)}")
                position = len(kept) if position is None else position
            else:
                remaining.append(entry)
        if remaining:
            kept.append({**group, "hooks": remaining} if len(remaining) != len(entries) else group)
    if not uninstall:
        mine = {"matcher": "Bash", "hooks": [handler()]}
        kept.insert(len(kept) if position is None else position, mine)
        if mine not in groups:
            report.append(f"add    PreToolUse Bash: {tilde(handler()['command'])}")
    if kept:
        hooks["PreToolUse"] = kept
    elif isinstance(hooks, dict):
        hooks.pop("PreToolUse", None)
        if not hooks:
            result.pop("hooks", None)
    return result


def render(settings: dict, ascii_only: bool) -> str:
    return json.dumps(settings, indent=2, ensure_ascii=ascii_only) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--settings", required=True, type=Path, help="the Claude Code settings file")
    parser.add_argument("--dry-run", action="store_true", help="print the diff, change nothing")
    parser.add_argument("--uninstall", action="store_true", help="remove mastack's handler only")
    args = parser.parse_args()

    path = args.settings.expanduser()
    print(tilde(str(path)))
    try:
        before = path.read_text(encoding="utf-8") if path.exists() else ""
        settings = json.loads(before) if before.strip() else {}
        if not isinstance(settings, dict):
            raise ValueError("not a JSON object")
        report: list[str] = []
        after_settings = updated(settings, args.uninstall, report)
    except (OSError, ValueError) as error:
        print(f"  refuse {tilde(str(path))}: {error}; nothing changed", file=sys.stderr)
        return 1
    after = render(after_settings, before.isascii())
    if after_settings == settings:
        print("  ok     hooks" if not args.uninstall else "  ok     no mastack hook")
        return 0
    for line in report:
        print(f"  {line}")
    if args.dry_run:
        sys.stdout.writelines(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                                   tilde(str(path)), tilde(str(path)) + " (after)"))
        return 0
    if path.exists():
        backup = path.with_name(f"{path.name}.mastack-backup-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)
        print(f"  backup {tilde(str(backup))}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.mastack-{os.getpid()}")
    temporary.write_text(after, encoding="utf-8")
    if path.exists():
        shutil.copymode(path, temporary)
    os.replace(temporary, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
