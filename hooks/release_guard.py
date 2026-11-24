#!/usr/bin/env python3
"""Release guard, a Claude Code PreToolUse[Bash] check: refuse releases and publishes without an owner go-ahead.

Why (2026-11-12): an agent published repo-kit 0.6.0 although the repository's publishing.md allows a release only
on an explicit request, and its brief said to stop with the release ready. Text rules were ignored, and dependent
repositories adopt releases automatically.

Denies, also inside chains, pipes, compound commands, command substitutions, `sh|bash|zsh -c` scripts and `eval`:
  - `npm publish`, `bun publish`, `pnpm publish` and `yarn npm publish` (not with `--dry-run`, `-h` or `--help`);
  - `bun|npm|pnpm|yarn run release:publish` (or `yarn release:publish`) and `repo-kit release` (also through
    `bunx`, `npx` or `pnpm dlx`);
  - `gh release create`;
  - `git push` of a `v*` tag (`v1.2.3`, `refs/tags/v1.2.3`, `<src>:refs/tags/v1.2.3`, or `--tags`), not `--delete`
    or `--dry-run`;
  - `lanefather` (or a declared `lanefather_commands` wrapper) `promote --ship`.

  - `gh workflow run` of a workflow whose name says release or publish;
  - owner-only steps: `gh repo edit --visibility`, `gh repo create --public`, `npm access` changes, and writes to a
    repository's Pages through `gh api`.

A command passes when one of two things holds for every release or publish in it:

1. Standing permission (2026-11-24, the owner's word: the gate, review and landing lock are the protection, not his
   "ok"). The project's `docs/agents/hooks.json`, as committed on `origin/main` (an unlanded edit does not count),
   names the packages it covers under `release_standing`, and local facts, read without the network, show the
   release is routine: the package is declared and an earlier `v*` tag exists (not a first publication); the step
   from the highest earlier `v*` tag is a patch or minor allowed by `levels` (never a major); the version's
   CHANGELOG section has no Breaking entry (before 1.0.0 a minor may be breaking, and the four projects' VERSIONING
   docs mark that with `### Breaking` or `Breaking:`); and an `--access` flag does not change the package's access.
   Whether the release gate passed on the commit is the project's publish command's check (package-kit's
   `release:publish` refuses without the gate's passed status); this hook does not repeat it.
2. Owner go-ahead: `MASTACK_RELEASE_OK` in the environment (not set in the command itself, so an agent cannot grant
   its own go-ahead by prefixing `MASTACK_RELEASE_OK=...`) carries `<package>@<version>`, `<version>` (`v1.2.3` or
   `1.2.3`) or `ship` matching it. Owner-only steps get no standing permission and no variable.

Otherwise the hook asks the owner on a permission card where that card is proven to reach a person (2026-11-24
probes: T3 Code Claude sessions in `default`, `acceptEdits` and `bypassPermissions` modes; T3 shows Claude's hook
`ask` as an approval card even in full access, and Claude Code refuses `ask` when no one can answer it), naming the
package, version, command and the missing fact. Everywhere else, Codex included (which rejects `ask`) and T3's
`auto` mode (which approves every call), it denies with that fact. Each allowed release is logged to guard.log.
Read like the shared shell reader reads the shell; a command it cannot parse passes.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import hook_io
import shell
from vocabulary import GIT_OPTIONS_WITH_VALUE, SHELLS

ENV_VAR = "MASTACK_RELEASE_OK"
DISPLAY = {"-h", "--help", "-V", "--version"}
DRY_RUN = {"--dry-run", "-n"}
# Valid go-ahead token: <package>@<version> (scoped or unscoped), v<version>, <semver>, or "ship".
TOKEN_RE = re.compile(
    r"^(?:@[A-Za-z0-9._-]+/[A-Za-z0-9._-]+|[A-Za-z0-9._-]+)@[vV]?\d+\.\d+\.\d+(?:-[A-Za-z0-9._-]+)?(?:\+[A-Za-z0-9._-]+)?$"
    r"|^[vV]?\d+\.\d+\.\d+(?:-[A-Za-z0-9._-]+)?(?:\+[A-Za-z0-9._-]+)?$"
    r"|^ship$"
)
VERSION_TOKEN_RE = re.compile(r"^[vV]?\d+\.\d+\.\d+(?:-[A-Za-z0-9._-]+)?(?:\+[A-Za-z0-9._-]+)?$")
BUMP_SPEC_RE = re.compile(
    r"^(?:([A-Za-z0-9._/@-]+):)?(?:(patch|minor|major)|([vV]?\d+\.\d+\.\d+(?:-[A-Za-z0-9._-]+)?))$"
)
V_TAG_RE = re.compile(r"^(?:refs/tags/)?(v\d[\w.+~^-]*)$")

NPM_VALUE = {"--tag", "--access", "--otp", "--registry", "--workspace", "-w", "-C", "--prefix", "--userconfig",
             "--cache", "--filter"}
YARN_VALUE = {"--cwd", "--tag", "--access", "--otp"}
RUN_MANAGERS = {"bun", "npm", "pnpm", "yarn"}
RUN_VALUE = {"--cwd", "-C", "--prefix", "--filter", "-F", "--workspace", "-w", "--config", "-c"}
EXEC_RUNNERS = {"bunx", "npx", "pnpx"}
EXEC_VALUE = {"-p", "--package"}
GH_VALUE = {"-R", "--repo", "-F", "--notes-file", "-n", "--notes", "-t", "--title", "--target",
            "--discussion-category", "--notes-from-tag", "--notes-start-tag"}
PUSH_OPTIONS_WITH_VALUE = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
TIMEOUT_VALUES = {"-s", "--signal", "-k", "--kill-after"}
XARGS_VALUES = {"-n", "-L", "-P", "-I", "-J", "-E", "-d", "-s", "-a", "-R", "-S"}
LEASED = {"slotfather": "run", "junkfather": "own"}
GH_VALUE |= {"-f", "--field", "-r", "--raw-field", "--ref", "-X", "--method", "--input", "-H", "--header"}

STANDING_KEY = "release_standing"
STANDING_REF = "origin/main"
STANDING_LEVELS = ("patch", "minor")
SEMVER_RE = re.compile(r"^[vV]?(\d+)\.(\d+)\.(\d+)$")
BREAKING_RE = re.compile(r"(?im)^###\s+breaking\b|\bbreaking:")
# Where a hook's `ask` was shown to reach a person or be refused, never auto-approved (see the module docstring).
CARD_ENTRYPOINTS = {"t3-code"}
CARD_MODES = {"default", "acceptEdits", "bypassPermissions"}
OWNER_ONLY = "owner-only"


def name_of(word) -> str:
    return (word.literal or "").rsplit("/", 1)[-1]


def program_path(word) -> str:
    return shell.program(word)


def after_options(args, values: set[str]) -> list:
    index = 0
    while index < len(args) and (args[index].literal or "").startswith("-"):
        option = args[index].literal or ""
        if option == "--":
            return args[index + 1:]
        index += 2 if option in values else 1
    return args[index:]


def unwrap_runners(words: list[shell.Word]) -> list[shell.Word]:
    """Unwrap env/nohup/sudo, timeout/gtimeout, xargs, and slotfather/junkfather leases."""
    own = shell.unwrap(words)
    while own:
        name, rest = name_of(own[0]), own[1:]
        if name in ("timeout", "gtimeout"):
            own = shell.unwrap(after_options(rest, TIMEOUT_VALUES)[1:])
        elif name == "xargs":
            own = shell.unwrap(after_options(rest, XARGS_VALUES))
        elif name in LEASED and rest and rest[0].literal == LEASED[name]:
            ends = [i for i, word in enumerate(rest) if word.literal == "--"]
            if not ends:
                break
            own = shell.unwrap(rest[ends[0] + 1:])
        else:
            break
    return own


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


def simple_commands(command: str, depth: int = 0):
    """Yield `(raw_words, unwrapped_words)` for every simple command, recursing into `sh -c` and `eval`."""
    if depth > 6:
        return
    for words in _walk(shell.read(command)):
        own = unwrap_runners(words)
        if not own:
            continue
        name = name_of(own[0])
        if name in SHELLS:
            literals = [w.literal or "" for w in own[1:]]
            at = next((i for i, w in enumerate(literals) if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", w)), None)
            script = next((own[1 + i] for i in range(at + 1, len(literals)) if not literals[i].startswith("-")),
                          None) if at is not None else None
            if script is not None and script.literal is not None:
                yield from simple_commands(script.literal, depth + 1)
                continue
        if name == "eval":
            text = " ".join(w.literal for w in own[1:] if w.literal is not None)
            if text:
                yield from simple_commands(text, depth + 1)
            continue
        yield words, own


def resolve_dir(current: str | None, target: str | None) -> str | None:
    if not target or "$" in target or "`" in target or "\0" in target:
        return current
    expanded = os.path.expanduser(target)
    if os.path.isabs(expanded):
        return os.path.realpath(expanded)
    return os.path.realpath(os.path.join(current, expanded)) if current else None


def read_package_json(path: str) -> tuple[str | None, str | None]:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    name = data.get("name") if isinstance(data.get("name"), str) and data.get("name").strip() else None
    version = data.get("version") if isinstance(data.get("version"), str) and data.get("version").strip() else None
    return name, version


def workspace_packages(cwd: str | None) -> list[tuple[str, str]]:
    """All `(name, version)` pairs from `cwd/package.json` and `cwd/packages/*/package.json`."""
    if not cwd:
        return []
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    candidates = [os.path.join(cwd, "package.json")]
    packages_dir = os.path.join(cwd, "packages")
    if os.path.isdir(packages_dir):
        try:
            for entry in sorted(os.listdir(packages_dir)):
                candidates.append(os.path.join(packages_dir, entry, "package.json"))
        except OSError:
            pass
    for candidate in candidates:
        real = os.path.realpath(candidate)
        if real in seen:
            continue
        seen.add(real)
        name, version = read_package_json(real)
        if name and version:
            found.append((name, version))
    return found


def lanefather_commands(cwd: str | None) -> list[str]:
    return (hook_io.strings(hook_io.config().get("lanefather_commands"))
            + hook_io.strings(hook_io.project_config(cwd).get("lanefather_commands")))


def has_help_or_dry_run(literals: list[str], allow_short_n: bool = False) -> bool:
    dry = DRY_RUN if allow_short_n else {"--dry-run"}
    return any(lit in DISPLAY or lit in dry for lit in literals)


def access_of(literals: list[str]) -> str | None:
    """The value of `--access` in a publish command, or None."""
    for index, arg in enumerate(literals):
        if arg == "--access" and index + 1 < len(literals):
            return literals[index + 1]
        if arg.startswith("--access="):
            return arg.split("=", 1)[1]
    return None


def detect_npm_access(own: list[shell.Word]) -> tuple[str, dict] | None:
    """Detect `npm access <change>` (not `get`, `list` or `ls`): it changes who can install a package."""
    if name_of(own[0]) != "npm":
        return None
    literals = [w.literal or "" for w in own[1:]]
    if any(lit in DISPLAY for lit in literals):
        return None
    rest = after_options(own[1:], NPM_VALUE)
    words = [w.literal or "" for w in rest]
    if len(words) >= 2 and words[0] == "access" and words[1] not in ("get", "list", "ls"):
        return OWNER_ONLY, {"what": "changes a package's access"}
    return None


def detect_package_publish(own: list[shell.Word], cwd: str | None) -> tuple[str, dict] | None:
    """Detect `npm|bun|pnpm publish` and `yarn npm publish`."""
    name = name_of(own[0])
    literals = [w.literal or "" for w in own[1:]]
    if has_help_or_dry_run(literals):
        return None
    directory = cwd
    if name in ("npm", "bun", "pnpm"):
        index = 0
        while index < len(literals):
            arg = literals[index]
            if arg in ("-C", "--prefix", "--cwd") and index + 1 < len(literals):
                directory = resolve_dir(directory, literals[index + 1])
                index += 2
                continue
            if any(arg.startswith(prefix) for prefix in ("--prefix=", "--cwd=")):
                directory = resolve_dir(directory, arg.split("=", 1)[1])
                index += 1
                continue
            if arg in NPM_VALUE:
                index += 2
                continue
            if arg.startswith("-"):
                index += 1
                continue
            break
        if index >= len(literals) or literals[index] != "publish":
            return None
        rest = literals[index + 1:]
        if has_help_or_dry_run(rest):
            return None
        for idx, arg in enumerate(rest):
            if arg in ("-C", "--prefix", "--cwd") and idx + 1 < len(rest):
                directory = resolve_dir(directory, rest[idx + 1])
            elif any(arg.startswith(prefix) for prefix in ("--prefix=", "--cwd=")):
                directory = resolve_dir(directory, arg.split("=", 1)[1])
        return "publish", {"cwd": directory, "access": access_of(literals)}
    if name == "yarn":
        index = 0
        while index < len(literals):
            arg = literals[index]
            if arg == "--cwd" and index + 1 < len(literals):
                directory = resolve_dir(directory, literals[index + 1])
                index += 2
                continue
            if arg.startswith("--cwd="):
                directory = resolve_dir(directory, arg.split("=", 1)[1])
                index += 1
                continue
            if arg in YARN_VALUE:
                index += 2
                continue
            if arg.startswith("-"):
                index += 1
                continue
            break
        if literals[index:index + 2] != ["npm", "publish"]:
            return None
        if has_help_or_dry_run(literals[index + 2:]):
            return None
        return "publish", {"cwd": directory, "access": access_of(literals)}
    return None


def detect_release_script_or_repo_kit(own: list[shell.Word], cwd: str | None) -> tuple[str, dict] | None:
    """Detect `bun run release:publish`, `repo-kit release` and `bunx/npx/pnpm dlx repo-kit release`."""
    name = name_of(own[0])
    literals = [w.literal or "" for w in own[1:]]
    if any(lit in DISPLAY for lit in literals):
        return None
    directory = cwd
    rest = literals
    if name in EXEC_RUNNERS:
        rest = [w.literal or "" for w in after_options(own[1:], EXEC_VALUE)]
        if not rest:
            return None
        pkg = rest[0].rsplit("/", 1)[-1].split("@", 1)[0]
        if pkg != "repo-kit":
            return None
        name, rest = "repo-kit", rest[1:]
    elif name in RUN_MANAGERS:
        index = 0
        while index < len(rest):
            arg = rest[index]
            if arg in ("--cwd", "-C", "--prefix") and index + 1 < len(rest):
                directory = resolve_dir(directory, rest[index + 1])
                index += 2
                continue
            if any(arg.startswith(p) for p in ("--cwd=", "--prefix=")):
                directory = resolve_dir(directory, arg.split("=", 1)[1])
                index += 1
                continue
            if arg in RUN_VALUE:
                index += 2
                continue
            if arg.startswith("-"):
                index += 1
                continue
            break
        tail = rest[index:]
        if not tail:
            return None
        if tail[0] in ("dlx", "exec", "x") and len(tail) >= 2:
            pkg = tail[1].rsplit("/", 1)[-1].split("@", 1)[0]
            if pkg == "repo-kit":
                name, rest = "repo-kit", tail[2:]
        if name != "repo-kit":
            script = tail[1] if tail[0] == "run" and len(tail) >= 2 else tail[0]
            script_args = tail[2:] if tail[0] == "run" else tail[1:]
            if script_args and script_args[0] == "--":
                script_args = script_args[1:]
            if script == "release:publish":
                if has_help_or_dry_run(script_args):
                    return None
                return "release:publish", {"cwd": directory}
            if script == "release":
                if has_help_or_dry_run(script_args):
                    return None
                return "repo-kit-release", {"cwd": directory, "specs": _bump_specs(script_args)}
            return None
    if name == "repo-kit":
        index = 0
        while index < len(rest) and rest[index].startswith("-"):
            index += 1
        if index >= len(rest):
            return None
        verb, verb_args = rest[index], rest[index + 1:]
        if has_help_or_dry_run(verb_args):
            return None
        if verb == "release":
            return "repo-kit-release", {"cwd": directory, "specs": _bump_specs(verb_args)}
        if verb == "publish":
            return "release:publish", {"cwd": directory}
    return None


def _bump_specs(args: list[str]) -> list[tuple[str | None, str | None, str | None]]:
    """`(package or None, explicit version or None, level or None)` per bump spec."""
    specs = []
    for arg in args:
        if arg == "--":
            continue
        match = BUMP_SPEC_RE.match(arg)
        if match:
            specs.append((match.group(1), match.group(3), match.group(2)))
    return specs


def detect_gh_release(own: list[shell.Word]) -> tuple[str, dict] | None:
    """Detect `gh release create [<tag>]`, `gh workflow run <release or publish workflow>`, and the owner-only
    `gh repo edit --visibility`, `gh repo create --public` and Pages writes through `gh api`."""
    if name_of(own[0]) != "gh":
        return None
    literals = [w.literal or "" for w in own[1:]]
    if any(lit in DISPLAY for lit in literals):
        return None
    positionals = []
    index = 0
    while index < len(literals):
        arg = literals[index]
        if arg == "--":
            positionals.extend(literals[index + 1:])
            break
        if arg in GH_VALUE:
            index += 2
            continue
        if arg.startswith("-"):
            index += 1
            continue
        positionals.append(arg)
        index += 1
    if positionals[:2] == ["workflow", "run"] and len(positionals) >= 3:
        workflow = positionals[2].rsplit("/", 1)[-1].lower()
        if "release" in workflow or "publish" in workflow:
            return "workflow", {"workflow": positionals[2]}
        return None
    if positionals[:2] == ["repo", "edit"] and any(lit.startswith("--visibility") for lit in literals):
        return OWNER_ONLY, {"what": "changes a repository's visibility"}
    if positionals[:2] == ["repo", "create"] and "--public" in literals:
        return OWNER_ONLY, {"what": "creates a public repository"}
    if positionals[:1] == ["api"] and any(re.search(r"/pages(?:/|$)", p) for p in positionals[1:]):
        method = next((literals[i + 1] for i, lit in enumerate(literals[:-1]) if lit in ("-X", "--method")), None)
        method = method or next((lit.split("=", 1)[1] for lit in literals if lit.startswith("--method=")), None)
        writes = any(lit in ("-f", "-F", "--field", "--raw-field", "--input") or
                     lit.startswith(("--field=", "--raw-field=", "--input=")) for lit in literals)
        if (method and method.upper() != "GET") or writes:
            return OWNER_ONLY, {"what": "changes a repository's Pages"}
        return None
    if positionals[:2] != ["release", "create"]:
        return None
    tag = positionals[2] if len(positionals) >= 3 else None
    return "gh-release", {"tag": tag}


def detect_git_tag_push(own: list[shell.Word]) -> tuple[str, dict] | None:
    """Detect `git push` of a `v*` tag (or `--tags`), excluding `--delete`, `-d`, `:tag` and `--dry-run`."""
    if name_of(own[0]) != "git":
        return None
    literals = [w.literal or "" for w in own[1:]]
    if any(lit in DISPLAY for lit in literals):
        return None
    index = 0
    while index < len(literals) and literals[index].startswith("-"):
        index += 2 if literals[index] in GIT_OPTIONS_WITH_VALUE else 1
    if index >= len(literals) or literals[index] != "push":
        return None
    rest = literals[index + 1:]
    if has_help_or_dry_run(rest, allow_short_n=True):
        return None
    positionals, pos, delete, all_tags = [], 0, False, False
    while pos < len(rest):
        word = rest[pos]
        if word == "--":
            positionals.extend(rest[pos + 1:])
            break
        if word in PUSH_OPTIONS_WITH_VALUE:
            pos += 2
            continue
        if word in ("-d", "--delete"):
            delete = True
        elif word == "--tags":
            all_tags = True
        elif not word.startswith("-"):
            positionals.append(word)
        pos += 1
    if delete:
        return None
    if all_tags:
        return "git-tag", {"tag": None}
    refspecs = positionals[1:] if len(positionals) >= 2 else positionals
    for refspec in refspecs:
        clean = refspec.lstrip("+")
        if ":" in clean:
            source, _, dest = clean.partition(":")
            if not source:  # `:refs/tags/v1.0.0` deletes the remote tag
                continue
            match = V_TAG_RE.match(dest)
        else:
            match = V_TAG_RE.match(clean)
        if match:
            return "git-tag", {"tag": match.group(1)}
    return None


def detect_lanefather_ship(own: list[shell.Word], lane_commands: list[str]) -> tuple[str, dict] | None:
    """Detect `lanefather promote --ship` (including global `--config` and declared `lanefather_commands`)."""
    raw_prog = program_path(own[0])
    base = raw_prog.rsplit("/", 1)[-1]
    is_lane = base == "lanefather" or any(raw_prog == alias or raw_prog.endswith("/" + alias) for alias in lane_commands)
    rest = [w.literal or "" for w in own[1:]]
    if not is_lane and base in ("python", "python3", "bash", "sh", "zsh") and len(own) > 1:
        sub = own[1:]
        while sub and (sub[0].literal or "").startswith("-"):
            if sub[0].literal in ("-c", "-n"):
                return None
            sub = sub[2:] if sub[0].literal in ("-W", "-X") else sub[1:]
        if sub:
            sub_prog = program_path(sub[0])
            sub_base = sub_prog.rsplit("/", 1)[-1]
            if sub_base == "lanefather" or any(
                    sub_prog == alias or sub_prog.endswith("/" + alias) for alias in lane_commands):
                is_lane = True
                rest = [w.literal or "" for w in sub[1:]]
    if not is_lane or has_help_or_dry_run(rest):
        return None
    pos = 0
    while pos < len(rest) and rest[pos].startswith("-"):
        if rest[pos] == "--config":
            pos += 2
        elif rest[pos].startswith("--config="):
            pos += 1
        else:
            return None
    remaining = rest[pos:]
    if not remaining or remaining[0] != "promote":
        return None
    options = {a.split("=", 1)[0] for a in remaining[1:]}
    if "--ship" in options:
        shas = [a for a in remaining[1:] if not a.startswith("-")]
        return "lanefather-ship", {"sha": shas[0] if shas else None}
    return None


def parse_tokens(value: str) -> list[str]:
    """Parse `$MASTACK_RELEASE_OK` into validated go-ahead tokens; returns [] if empty or any token is invalid."""
    raw_tokens = [t.strip() for t in re.split(r"[\s,]+", value.strip()) if t.strip()]
    if not raw_tokens or not all(TOKEN_RE.match(t) for t in raw_tokens):
        return []
    return raw_tokens


def token_parts(token: str) -> tuple[str | None, str | None]:
    """`(package_or_None, normalized_version_or_None)` for a valid go-ahead token."""
    if token == "ship":
        return None, None
    if "@" in token and not token.startswith("@"):
        pkg, ver = token.split("@", 1)
        return pkg, ver.lstrip("vV")
    if token.startswith("@") and "@" in token[1:]:
        pkg, ver = token.rsplit("@", 1)
        return pkg, ver.lstrip("vV")
    return None, token.lstrip("vV")


def authorized(kind: str, info: dict, tokens: list[str]) -> bool:
    """Whether `tokens` from `MASTACK_RELEASE_OK` authorize the detected release/publish action."""
    if not tokens:
        return False
    parsed = [token_parts(t) for t in tokens]
    pkg_tokens = [(pkg, ver) for pkg, ver in parsed if pkg is not None and ver is not None]
    ver_tokens = [ver for pkg, ver in parsed if pkg is None and ver is not None]

    if kind in ("publish", "release:publish"):
        packages = workspace_packages(info.get("cwd"))
        if packages:
            for pkg_name, pkg_ver in packages:
                short_name = pkg_name.split("/", 1)[-1]
                for tok_pkg, tok_ver in pkg_tokens:
                    if (tok_pkg == pkg_name or tok_pkg == short_name) and tok_ver == pkg_ver.lstrip("vV"):
                        return True
            return False
        return bool(pkg_tokens)

    if kind == "repo-kit-release":
        specs = info.get("specs") or []
        packages = workspace_packages(info.get("cwd"))
        if any(spec[0] is not None for spec in specs):
            named = [spec for spec in specs if spec[0] is not None]
            if not named:
                specs = []
            for spec_pkg, spec_ver, _ in named:
                matched = False
                for tok_pkg, tok_ver in pkg_tokens:
                    tok_short = tok_pkg.split("/", 1)[-1]
                    if spec_pkg in (tok_pkg, tok_short):
                        if spec_ver is None or spec_ver.lstrip("vV") == tok_ver:
                            matched = True
                            break
                if not matched:
                    return False
            return True
        if packages:
            pkg_names = {p for p, _ in packages} | {p.split("/", 1)[-1] for p, _ in packages}
            return any(tok_pkg in pkg_names for tok_pkg, _ in pkg_tokens)
        return bool(pkg_tokens)

    if kind in ("gh-release", "git-tag"):
        tag = info.get("tag")
        if not tag:
            return False
        norm_tag = tag.lstrip("vV")
        return any(ver == norm_tag for _, ver in parsed if ver is not None)

    if kind == "lanefather-ship":
        return "ship" in tokens or bool(pkg_tokens) or bool(ver_tokens)

    return False


def command_sets_env_var(raw_words: list[shell.Word], full_command: str) -> bool:
    """True when the command itself assigns or exports `MASTACK_RELEASE_OK`."""
    if ENV_VAR not in full_command:
        return False
    for word in raw_words:
        if word.raw.startswith(f"{ENV_VAR}=") or f"{ENV_VAR}=" in word.raw:
            return True
    return bool(re.search(rf"\b{ENV_VAR}\s*=", full_command))


def actions(command: str, cwd: str | None) -> tuple[list[tuple[str, str, dict]], bool]:
    """`([(shown, kind, info), ...], self_assigned)` for all release/publish commands in `command`."""
    found: list[tuple[str, str, dict]] = []
    self_assigned = bool(re.search(rf"\b{ENV_VAR}\s*=", command))
    lane_cmds = lanefather_commands(cwd)
    current = cwd
    for raw_words, own in simple_commands(command):
        if command_sets_env_var(raw_words, command):
            self_assigned = True
        name = name_of(own[0])
        if name == "cd" and len(own) > 1 and own[1].literal:
            current = resolve_dir(current, own[1].literal)
            continue
        hit = (detect_package_publish(own, current)
               or detect_npm_access(own)
               or detect_release_script_or_repo_kit(own, current)
               or detect_gh_release(own)
               or detect_git_tag_push(own)
               or detect_lanefather_ship(own, lane_cmds))
        if hit is not None:
            info = dict(hit[1])
            info.setdefault("cwd", current)
            found.append((shell.show(own), hit[0], info))
    return found, self_assigned


# ---- standing permission ------------------------------------------------------------------------------------------

class Missing(Exception):
    """A fact the standing permission needs is missing; the message names it for the refusal and the card."""


def git(cwd: str, *args: str) -> str | None:
    """Output of a read-only, local git command in `cwd`, or None when it fails or the hook's time is spent."""
    try:
        proc = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True,
                              timeout=hook_io.timeout(3), stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError, hook_io.OutOfTime):
        return None
    return proc.stdout if proc.returncode == 0 else None


def standing(cwd: str) -> tuple[set[str], tuple[str, ...]]:
    """`(declared packages, allowed levels)` from `release_standing` in the project's docs/agents/hooks.json as
    committed on origin/main."""
    text = git(cwd, "show", f"{STANDING_REF}:{hook_io.PROJECT_FILE}")
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        data = {}
    declared = data.get(STANDING_KEY) if isinstance(data, dict) else None
    if not isinstance(declared, dict):
        raise Missing(f"the project gives no standing permission: no `{STANDING_KEY}` in {hook_io.PROJECT_FILE} on "
                      f"{STANDING_REF}")
    packages = set(hook_io.strings(declared.get("packages")))
    levels = tuple(level for level in hook_io.strings(declared.get("levels")) or STANDING_LEVELS
                   if level in STANDING_LEVELS)
    return packages, levels


def package_entries(cwd: str | None) -> list[dict]:
    """`{name, version, dir, data}` for `cwd/package.json` and `cwd/packages/*/package.json` that are not private."""
    if not cwd:
        return []
    entries, seen = [], set()
    candidates = [os.path.join(cwd, "package.json")]
    packages_dir = os.path.join(cwd, "packages")
    if os.path.isdir(packages_dir):
        candidates += [os.path.join(packages_dir, entry, "package.json") for entry in sorted(os.listdir(packages_dir))]
    for candidate in candidates:
        real = os.path.realpath(candidate)
        if real in seen:
            continue
        seen.add(real)
        try:
            with open(real, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("name"), str) and data.get("private") is not True:
            entries.append({"name": data["name"], "version": str(data.get("version") or ""), "dir": os.path.dirname(real),
                            "data": data})
    return entries


def semver(text: str | None) -> tuple[int, int, int] | None:
    match = SEMVER_RE.match(text or "")
    return tuple(int(part) for part in match.groups()) if match else None


def bump(version: tuple[int, int, int], level: str) -> tuple[int, int, int]:
    major, minor, patch = version
    return {"major": (major + 1, 0, 0), "minor": (major, minor + 1, 0), "patch": (major, minor, patch + 1)}[level]


def shown_version(version: tuple[int, int, int]) -> str:
    return ".".join(map(str, version))


def changelog_section(entry: dict, cwd: str, heading: str) -> str:
    """The CHANGELOG section headed `## <heading>` of the package, else of the repository."""
    pattern = re.compile(rf"^##\s+\[?v?{re.escape(heading)}\]?(?:\s|$)", re.IGNORECASE)
    for path in (os.path.join(entry["dir"], "CHANGELOG.md"), os.path.join(cwd, "CHANGELOG.md")):
        try:
            with open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        except OSError:
            continue
        for index, line in enumerate(lines):
            if pattern.match(line):
                end = next((j for j in range(index + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
                return "\n".join(lines[index + 1:end])
    raise Missing(f"no `## {heading}` section in the CHANGELOG of {entry['name']}")


def routine(entry: dict, cwd: str, target: tuple[int, int, int] | None, heading: str, levels: tuple[str, ...],
            access: str | None = None) -> str:
    """The level of a routine release of `entry` at `target`, or Missing naming what makes it the owner's call."""
    name = entry["name"]
    if target is None:
        raise Missing(f"cannot read a plain x.y.z version for {name}")
    tags = git(cwd, "tag", "--list", "v*")
    if tags is None:
        raise Missing(f"cannot read the repository's `v*` tags for {name}")
    earlier = [version for version in (semver(tag.strip()) for tag in tags.splitlines()) if version and version < target]
    if not earlier:
        raise Missing(f"no `v*` tag before {shown_version(target)}: a first publication of {name} is the owner's call")
    previous = max(earlier)
    if target[0] != previous[0]:
        level = "major"
    elif target[1] != previous[1]:
        level = "minor"
    else:
        level = "patch"
    if level not in levels:
        raise Missing(f"{name} {shown_version(previous)} -> {shown_version(target)} is a {level} step; the standing "
                      f"permission covers {' and '.join(levels) or 'no level'}")
    if BREAKING_RE.search(changelog_section(entry, cwd, heading)):
        raise Missing(f"the CHANGELOG section `## {heading}` of {name} has a Breaking entry: a breaking change is the "
                      "owner's call")
    if access is not None:
        current = (entry["data"].get("publishConfig") or {}).get("access") if isinstance(
            entry["data"].get("publishConfig"), dict) else None
        configs = ("package-kit.config.mjs", "repo-kit.config.mjs")
        configured = any(f'access: "{access}"' in _read(os.path.join(cwd, config)) for config in configs)
        if access != current and not configured:
            raise Missing(f"`--access {access}` changes how {name} is published: access is the owner's call")
    return level


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def covered(cwd: str, packages: set[str]) -> list[dict]:
    """The publishable packages in `cwd`, all of them declared; Missing otherwise."""
    entries = package_entries(cwd)
    if not entries:
        raise Missing("no publishable package.json to classify")
    undeclared = [e["name"] for e in entries if e["name"] not in packages]
    if undeclared:
        raise Missing(f"{', '.join(undeclared)} not declared under `{STANDING_KEY}` on {STANDING_REF}")
    return entries


def standing_verdict(kind: str, info: dict, cwd: str | None) -> list[str]:
    """`pkg@version (level)` labels when the standing permission covers the action; Missing otherwise."""
    if kind == OWNER_ONLY:
        raise Missing(f"it {info.get('what')}: that is the owner's command each time")
    directory = info.get("cwd") or cwd
    if not directory or git(directory, "rev-parse", "--git-dir") is None:
        raise Missing("not inside a Git repository")
    packages, levels = standing(directory)
    if kind in ("publish", "release:publish", "workflow"):
        return [f"{e['name']}@{e['version']} ({routine(e, directory, semver(e['version']), e['version'], levels, info.get('access'))})"
                for e in covered(directory, packages)]
    if kind == "lanefather-ship":
        if info.get("sha"):
            wanted, head = git(directory, "rev-parse", f"{info['sha']}^{{commit}}"), git(directory, "rev-parse", "HEAD")
            if not wanted or wanted != head:
                raise Missing(f"{info['sha']} is not this checkout's HEAD, so its versions cannot be read here")
        return [f"{e['name']}@{e['version']} ({routine(e, directory, semver(e['version']), e['version'], levels)})"
                for e in covered(directory, packages)]
    if kind in ("git-tag", "gh-release"):
        target = semver(info.get("tag"))
        if target is None:
            raise Missing("cannot read a plain vX.Y.Z tag (`--tags` pushes every tag)")
        matching = [e for e in covered(directory, packages) if semver(e["version"]) == target]
        if not matching:
            raise Missing(f"no declared package has version {shown_version(target)}")
        return [f"{e['name']}@{e['version']} ({routine(e, directory, target, e['version'], levels)})" for e in matching]
    if kind == "repo-kit-release":
        entries = covered(directory, packages)
        specs = info.get("specs") or []
        if not specs:
            raise Missing("the bump level is not in the command")
        labels = []
        for spec_pkg, spec_ver, level in specs:
            pick = [e for e in entries if spec_pkg in (None, e["name"], e["name"].split("/", 1)[-1])]
            if len(pick) != 1:
                raise Missing(f"cannot tell which package `{spec_pkg or level}` bumps")
            current = semver(pick[0]["version"])
            if current is None:
                raise Missing(f"cannot read the current version of {pick[0]['name']}")
            target = semver(spec_ver) if spec_ver else bump(current, level)
            labels.append(f"{pick[0]['name']}@{shown_version(target) if target else spec_ver} "
                          f"({routine(pick[0], directory, target, 'Unreleased', levels)})")
        return labels
    raise Missing("this kind of release has no standing permission")


def card_reaches_owner(data: dict) -> bool:
    """Whether a PreToolUse `ask` reaches a person here (or is refused), never an automatic approval."""
    if "turn_id" in data:  # Codex: rejects `ask`
        return False
    return (os.environ.get("CLAUDE_CODE_ENTRYPOINT") in CARD_ENTRYPOINTS
            and data.get("permission_mode") in CARD_MODES)


def check(data: dict):
    command = hook_io.command_of(data)
    if command is None:
        return None
    cwd_raw = data.get("cwd")
    cwd = os.path.realpath(cwd_raw) if isinstance(cwd_raw, str) and cwd_raw else None
    try:
        found, self_assigned = actions(command, cwd)
    except (shell.Unreadable, ValueError, IndexError, StopIteration, RecursionError):
        return None
    if not found:
        return None
    env_value = os.environ.get(ENV_VAR, "").strip()
    tokens = [] if self_assigned else parse_tokens(env_value)
    blocked = []
    for shown, kind, info in found:
        if kind != OWNER_ONLY and authorized(kind, info, tokens):
            hook_io.log("guard.log", f"release-guard ok={env_value!r} cwd={cwd} command={shown!r}")
            continue
        try:
            labels = standing_verdict(kind, info, cwd)
        except Missing as missing:
            blocked.append((shown, str(missing)))
            continue
        except Exception as error:  # noqa: BLE001 - a classification bug refuses; it never lets a release through
            blocked.append((shown, f"the guard could not classify it ({error!r})"))
            continue
        hook_io.log("guard.log", f"release-guard standing {', '.join(labels)} cwd={cwd} command={shown!r}")
    if not blocked:
        return None
    lines = [f"- `{shown}`: {fact}" for shown, fact in dict.fromkeys(blocked)]
    if not self_assigned and card_reaches_owner(data):
        return hook_io.ask(
            "release-guard: the owner's approval is needed for this release or publish; approve only if you want it "
            "out now.\n" + "\n".join(lines))
    note = ""
    if self_assigned:
        note = (f"\nSetting `{ENV_VAR}` inside the command itself does not count: only the owner can grant it in the "
                "session environment before the command runs.")
    elif env_value:
        note = f"\n`{ENV_VAR}={env_value}` in the environment does not match what this command releases or publishes."
    return hook_io.deny(
        "release-guard denied this command: registry versions and promoted releases cannot be unsent and downstream "
        "repositories adopt them automatically, and the standing permission for routine releases does not cover "
        "it.\n"
        + "\n".join(lines)
        + note
        + f"\nOnly the owner can grant it: set `{ENV_VAR}=<package>@<version>` in the environment before starting "
        f"the release command (or `<version>` for a tag/GitHub release, `ship` for `lanefather promote --ship`), or "
        "approve the permission card where the session shows one (T3 Code Claude sessions in default, accept-edits "
        f"or full-access mode). Agents must never set `{ENV_VAR}` themselves; here, stop with the release ready and "
        "ask the owner, naming the fact above.")


if __name__ == "__main__":
    sys.exit(hook_io.run("release-guard", check))
