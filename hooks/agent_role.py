#!/usr/bin/env python3
"""PreToolUse hook for Agent: fill missing model and effort from models.toml for a known role.

    hooks/agent_role.py < hook.json

Reads the launch's role from an explicit marker in the prompt (`Role: <role>` or `[role: <role>]`) or from the
description (`[role: <role>]`, `role: <role>`, `[<role>]`, or a leading `<role>` word, with `implementer` ->
`implement` and `reviewer` -> `review`). When the role is defined in `models.toml` and has a Claude choice, any
missing `model` or `effort` in `tool_input` is filled in via `updatedInput`. Explicit `model` and `effort` values
already passed on the launch are kept; a launch without a known role passes through unchanged.

Fails open on malformed input or an unreadable table.
"""
from __future__ import annotations

import re
import sys

import hook_io
import model_roles

HOOK_TIMEOUT = 10  # seconds, as bin/install registers the hook

ROLE_ALIASES = {
    "implementer": "implement",
    "reviewer": "review",
    "specifier": "specify",
    "advisor": "specify",
    "critic": "critique",
}

TAG_ROLE_RE = re.compile(r"(?i)\[role\s*:\s*([a-z][a-z0-9_-]*)\]")
LINE_ROLE_RE = re.compile(r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?role(?:\*\*)?\s*:\s*([a-z][a-z0-9_-]*)\b")
DESC_PREFIX_RE = re.compile(r"(?i)^\s*(?:\[([a-z][a-z0-9_-]*)\]|([a-z][a-z0-9_-]*)(?:\s*[:\-—]\s*|\s+|$))")


def _match_explicit(text: str, known_roles: set[str]) -> str | None:
    best: tuple[int, str] | None = None
    for pattern in (LINE_ROLE_RE, TAG_ROLE_RE):
        for match in pattern.finditer(text):
            raw = match.group(1).lower()
            candidate = ROLE_ALIASES.get(raw, raw)
            if candidate in known_roles:
                pos = match.start()
                if best is None or pos < best[0]:
                    best = (pos, candidate)
                break
    return best[1] if best is not None else None


def extract_role(tool_input: dict, known_roles: set[str]) -> str | None:
    """Return the role named by `tool_input`, or None when none matches `known_roles`."""
    prompt = tool_input.get("prompt")
    if isinstance(prompt, str) and prompt:
        found = _match_explicit(prompt, known_roles)
        if found:
            return found
    description = tool_input.get("description")
    if isinstance(description, str) and description:
        found = _match_explicit(description, known_roles)
        if found:
            return found
        match = DESC_PREFIX_RE.match(description)
        if match:
            word = (match.group(1) or match.group(2) or "").lower()
            candidate = ROLE_ALIASES.get(word, word)
            if candidate in known_roles:
                return candidate
    return None


def claude_choice(table: dict, role: str) -> tuple[str, str] | None:
    """(model_id, effort) for the first Claude choice of `role` in `table`, or None."""
    entry = model_roles.role_of(table, role)
    only = entry.get("only_families")
    for choice in entry["choices"]:
        if not isinstance(choice, dict):
            continue
        model = model_roles.model_of(table, choice.get("model"))
        if isinstance(only, list) and model["family"] not in only:
            continue
        if model["cli"] != "claude":
            continue
        return model["id"], str(choice.get("effort") or "medium")
    return None


def check(data: dict) -> hook_io.Answer | None:
    if not isinstance(data, dict) or data.get("tool_name") != "Agent":
        return None
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    table = model_roles.load()
    known_roles = set(table["roles"])
    role = extract_role(tool_input, known_roles)
    if not role:
        return None
    picked = claude_choice(table, role)
    if not picked:
        return None
    model_id, effort = picked
    updated = dict(tool_input)
    changed = False
    if not isinstance(updated.get("model"), str) or not updated["model"].strip():
        updated["model"] = model_id
        changed = True
    if not isinstance(updated.get("effort"), str) or not updated["effort"].strip():
        updated["effort"] = effort
        changed = True
    return hook_io.Answer(None, updated) if changed else None


if __name__ == "__main__":
    sys.exit(hook_io.run("agent-role", check))
