#!/usr/bin/env python3
"""Release guard, a Claude Code PreToolUse[Bash] check: refuse releases and publishes without an owner go-ahead.

Why (2026-11-12): an agent published repo-kit 0.6.0 although the repository's publishing.md allows a release only
on an explicit request, and its brief said to stop with the release ready. Text rules were ignored, and dependent
repositories adopt releases automatically.

Denies, also inside chains, pipes, compound commands, command substitutions, `sh|bash|zsh -c` scripts and `eval`:
  - `npm publish`, `bun publish`, `pnpm publish` and `yarn npm publish` (not with `--dry-run`, `-h` or `--help`);
  - `bun|npm|pnpm|yarn run[-script] [options] release:publish|release` (or `yarn release:publish`), and
    `repo-kit|package-kit release|publish` (also through `bunx`, `npx`, `pnpx` or `pnpm|bun dlx|exec|x`);
  - `gh release create`, and a release created through `gh api .../releases`;
  - `gh workflow run` of a workflow named for a release, publish or promote, or named by number, and a dispatch
    through `gh api .../actions/workflows/<id>/dispatches`;
  - `git push` of `v*` tags (every refspec, `V` too, globs, `--tags`, `--follow-tags`, `-c push.followTags=true`),
    not `--delete` or `--dry-run`;
  - `lanefather` (or a declared `lanefather_commands` wrapper) `promote --ship`;
  - owner-only steps, which no variable and no standing permission cover: `gh repo edit --visibility`, `gh repo
    create --public`, `gh api` writes to a repository's visibility or Pages (last `-X` wins, attached short flags,
    query strings), and access changes (`npm access <change>`, `npm|pnpm config set access`, `npm pkg set
    publishConfig.access`, `npm_config_access=`).

A command passes when one of two things holds for every release or publish in it:

1. Standing permission (2026-11-24, the owner's word: the gate, review and landing lock are the protection, not his
   "ok"). An allowlist of shapes, not a list of tricks: the whole command is one of the plain release commands the
   projects' publishing docs use (`PLAIN_FORMS`), plain words with nothing beside it, run from the repository root
   of a clean checkout. The facts come from Git objects, not the working tree: the opt-in is `release_standing` in
   `docs/agents/hooks.json` of the commit the remote's main points at (`git ls-remote origin`, one network read,
   about 0.7-0.9 s, capped at REMOTE_SECONDS; unreachable means no standing pass); the release commit is HEAD, and
   for a publish it must be the remote's main; the repository has exactly one publishable package, declared there;
   the previous version is the highest `v*` tag that exists on the remote at an ancestor of the release commit (a
   local tag counts for nothing; none means a first publication, the owner's call); the step from it is a patch or
   minor allowed by `levels` (`[]` allows none); the version's CHANGELOG section exists and has no Breaking entry
   (before 1.0.0 a minor may be breaking; BREAKING_RE errs toward refusing); and the package's access settings are
   those of the previous release. Whether the release gate passed on the commit is the publish command's own check
   (package-kit's `release:publish` refuses without the gate's passed status; the npm projects' release workflow
   runs `verify --release` first); this hook does not repeat it.
2. Owner go-ahead: `MASTACK_RELEASE_OK` in the environment (not set in the command itself, so an agent cannot grant
   its own go-ahead by prefixing `MASTACK_RELEASE_OK=...`) carries `<package>@<version>`, `<version>` (`v1.2.3` or
   `1.2.3`) or `ship` matching it.

Otherwise the hook asks the owner on a permission card where that card is proven to reach a person (2026-11-24
probes: T3 Code Claude sessions in `default`, `acceptEdits` and `bypassPermissions` modes, not a subagent; T3 shows
Claude's hook `ask` as an approval card even in full access, and Claude Code refuses `ask` when no one can answer
it), naming the command and the missing fact. Everywhere else, Codex included (which rejects `ask`) and T3's `auto`
mode (which approves every call), it denies with that fact; the owner-only refusal does not offer the variable.
Each allowed release is logged to guard.log. A command the shell reader cannot parse is refused when it names a
release step, and passes otherwise. This is a seatbelt in the agent's shell, not a boundary: a script, an API call
or another tool can still publish.
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
V_TAG_RE = re.compile(r"^(?:refs/tags/)?([vV]\d[\w.+~^-]*)$")
KIT_TOOLS = {"repo-kit", "package-kit"}
RELEASE_WORKFLOW_RE = re.compile(r"release|publish|promote", re.IGNORECASE)

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
STANDING_LEVELS = ("patch", "minor")
REMOTE_SECONDS = 4.0
SEMVER_RE = re.compile(r"^[vV]?(\d+)\.(\d+)\.(\d+)$")
# Errs toward refusing: a Breaking heading at any depth, `- Breaking:`, `- **Breaking**:`, `BREAKING CHANGE:`,
# `Breaking change:` and an inline `Breaking:`, but not a longer word such as `line-breaking:`.
BREAKING_RE = re.compile(
    r"(?im)^#{2,6}[^\n]*\bbreaking\b"
    r"|^\s*(?:[-*+]\s+)?(?:\*\*|__)?breaking(?:[ _-]+changes?)?(?:\*\*|__)?\s*:"
    r"|(?<![\w-])breaking(?:[ _-]+changes?)?\s*(?:\*\*|__)?\s*:")
# The standing permission's command shapes: plain words, one command (see standing_shape).
SAFE_COMMAND_RE = re.compile(r"[A-Za-z0-9_@:./=~+-]+(?:[ \t]+[A-Za-z0-9_@:./=~+-]+)*")
REVIEW_START_RE = re.compile(r"[A-Z][A-Z0-9_]*_REVIEW_START=manual")
SHA_RE = re.compile(r"[0-9a-f]{7,40}")
CUT_SPEC_RE = re.compile(r"(?:([A-Za-z0-9._@/-]+):)?(patch|minor|major)")
PLAIN_FORMS = ("`bun run release -- [<package>:]<patch|minor>`, `bun run release:publish`, "
               "`gh workflow run release-npm.yml --ref main` and `lanefather promote <sha> --ship`")
# A command the shell reader cannot parse is refused when it holds one of these (quotes and backslashes removed).
RELEASE_WORDS_RE = re.compile(r"(?i)publish|release|--ship|visibility|--public|/pages|\baccess\b|--tags|follow-?tags"
                              r"|refs/tags/")
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


def package_entries(read, listdir, root: str = "") -> list[dict]:
    """`{name, version, dir, data, private}` for `root/package.json` and `root/packages/*/package.json`, read through
    `read(path) -> text | None` and `listdir(path) -> names`: the working tree or a commit (`git_reader`)."""
    entries = []
    candidates = ["package.json"] + [f"packages/{name}/package.json" for name in sorted(listdir("packages"))]
    for candidate in candidates:
        text = read(candidate)
        try:
            data = json.loads(text) if text else None
        except ValueError:
            continue
        name = data.get("name") if isinstance(data, dict) else None
        if not isinstance(name, str) or not name.strip():
            continue
        version = data.get("version")
        entries.append({"name": name, "version": version.strip() if isinstance(version, str) else "",
                        "dir": os.path.dirname(candidate), "data": data, "private": data.get("private") is True})
    return entries


def tree_reader(cwd: str):
    """`(read, listdir)` over the working tree at `cwd`."""
    def read(path):
        try:
            with open(os.path.join(cwd, path), encoding="utf-8") as handle:
                return handle.read()
        except (OSError, UnicodeDecodeError):
            return None

    def listdir(path):
        try:
            return [name for name in os.listdir(os.path.join(cwd, path)) if os.path.isdir(os.path.join(cwd, path, name))]
        except OSError:
            return []
    return read, listdir


def workspace_packages(cwd: str | None) -> list[tuple[str, str]]:
    """All `(name, version)` pairs from `cwd/package.json` and `cwd/packages/*/package.json`, private ones too."""
    if not cwd:
        return []
    return [(e["name"], e["version"]) for e in package_entries(*tree_reader(cwd)) if e["version"]]


def lanefather_commands(cwd: str | None) -> list[str]:
    return (hook_io.strings(hook_io.config().get("lanefather_commands"))
            + hook_io.strings(hook_io.project_config(cwd).get("lanefather_commands")))


def has_help_or_dry_run(literals: list[str], allow_short_n: bool = False) -> bool:
    dry = DRY_RUN if allow_short_n else {"--dry-run"}
    return any(lit in DISPLAY or lit in dry for lit in literals)


def access_of(literals: list[str]) -> str | None:
    """The value of the last `--access` in a publish command, as the package managers read it, or None."""
    found = None
    for index, arg in enumerate(literals):
        if arg == "--access" and index + 1 < len(literals):
            found = literals[index + 1]
        elif arg.startswith("--access="):
            found = arg.split("=", 1)[1]
    return found


def detect_npm_access(own: list[shell.Word], raw: list[shell.Word] | None = None) -> tuple[str, dict] | None:
    """Detect a change to who can install a package: `npm access <change>` (not `get`, `list` or `ls`),
    `npm|pnpm config set access`, `yarn config set npmPublishAccess`, `npm pkg set publishConfig.access`, and an
    `npm_config_access` assignment before the command."""
    if any(re.match(r"(?i)npm_config_access=", word.raw or "") for word in raw or ()):
        return OWNER_ONLY, {"what": "changes a package's access"}
    name = name_of(own[0])
    if name not in ("npm", "pnpm", "yarn"):
        return None
    literals = [w.literal or "" for w in own[1:]]
    if any(lit in DISPLAY for lit in literals):
        return None
    words = after_words(literals, NPM_VALUE)
    if len(words) >= 2 and words[0] == "access" and words[1] not in ("get", "list", "ls"):
        return OWNER_ONLY, {"what": "changes a package's access"}
    if len(words) >= 3 and words[0] == "config" and words[1] == "set" and \
            words[2].split("=", 1)[0].lower() in ("access", "npmpublishaccess"):
        return OWNER_ONLY, {"what": "changes a package's access"}
    if len(words) >= 3 and words[0] == "pkg" and words[1] == "set" and \
            any(word.startswith("publishConfig.access") for word in words[2:]):
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
    """Detect `bun|npm|pnpm|yarn run[-script] [options] release:publish|release`, `repo-kit|package-kit release|publish`
    and those tools through `bunx`, `npx`, `pnpx` or `pnpm|bun dlx|exec|x` (options before the package included)."""
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
        if pkg not in KIT_TOOLS:
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
            runner_rest = after_words(tail[1:], EXEC_VALUE)
            pkg = runner_rest[0].rsplit("/", 1)[-1].split("@", 1)[0] if runner_rest else ""
            if pkg in KIT_TOOLS:
                name, rest = "repo-kit", runner_rest[1:]
        if name != "repo-kit":
            runs = tail[0] in ("run", "run-script")
            script_words = after_words(tail[1:], RUN_VALUE) if runs else tail
            if not script_words:
                return None
            script, script_args = script_words[0], script_words[1:]
            if script_args and script_args[0] == "--":
                script_args = script_args[1:]
            if script == "release:publish":
                if has_help_or_dry_run(script_args):
                    return None
                return "release:publish", {"cwd": directory, "access": access_of(script_args)}
            if script == "release":
                if has_help_or_dry_run(script_args):
                    return None
                return "repo-kit-release", {"cwd": directory, "specs": _bump_specs(script_args)}
            return None
    if name in KIT_TOOLS:
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
            return "release:publish", {"cwd": directory, "access": access_of(verb_args)}
    return None


def after_words(words: list[str], values: set[str]) -> list[str]:
    """`words` after leading options (and the values of those in `values`)."""
    index = 0
    while index < len(words) and words[index].startswith("-"):
        if words[index] == "--":
            return words[index + 1:]
        index += 2 if words[index] in values else 1
    return words[index:]


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


def gh_words(literals: list[str]) -> list[str]:
    """`gh` arguments with attached short values split (`-XPOST` -> `-X POST`, `-fkey=v` -> `-f key=v`)."""
    split = []
    for arg in literals:
        if len(arg) > 2 and arg[0] == "-" and arg[1] in "XfFHRr":
            split += [arg[:2], arg[2:]]
        else:
            split.append(arg)
    return split


def detect_gh_release(own: list[shell.Word]) -> list[tuple[str, dict]]:
    """Detect `gh release create [<tag>]`, `gh workflow run` of a release, publish or promote workflow (or one named
    by number), release creation and workflow dispatch through `gh api`, and the owner-only steps: `gh repo edit
    --visibility`, `gh repo create --public`, and `gh api` writes to a repository's visibility or Pages. The last
    `-X`/`--method` wins, as in `gh`."""
    if name_of(own[0]) != "gh":
        return []
    literals = gh_words([w.literal or "" for w in own[1:]])
    if any(lit in DISPLAY for lit in literals):
        return []
    positionals, options, index = [], [], 0
    while index < len(literals):
        arg = literals[index]
        if arg == "--":
            positionals.extend(literals[index + 1:])
            break
        if arg in GH_VALUE and index + 1 < len(literals):
            options.append((arg, literals[index + 1]))
            index += 2
            continue
        if arg.startswith("--") and "=" in arg:
            options.append(tuple(arg.split("=", 1)))
        elif arg.startswith("-"):
            options.append((arg, None))
        else:
            positionals.append(arg)
        index += 1
    flags = {flag for flag, _ in options}
    if positionals[:2] == ["workflow", "run"] and len(positionals) >= 3:
        workflow = positionals[2].rsplit("/", 1)[-1].lower()
        if RELEASE_WORKFLOW_RE.search(workflow) or workflow.isdigit():
            return [("workflow", {"workflow": positionals[2]})]
        return []
    if positionals[:2] == ["repo", "edit"] and "--visibility" in flags:
        return [(OWNER_ONLY, {"what": "changes a repository's visibility"})]
    if positionals[:2] == ["repo", "create"] and any(
            flag == "--public" and value not in ("false", "0") for flag, value in options):
        return [(OWNER_ONLY, {"what": "creates a public repository"})]
    if positionals[:1] == ["api"] and len(positionals) >= 2:
        path = positionals[1].split("?", 1)[0].strip("/")
        methods = [value for flag, value in options if flag in ("-X", "--method") and value]
        fields = [value or "" for flag, value in options if flag in ("-f", "-F", "--field", "--raw-field", "--input")]
        method = (methods[-1] if methods else ("POST" if fields else "GET")).upper()
        if method == "GET":
            return []
        parts = path.split("/")
        if parts[:1] != ["repos"] or len(parts) < 3:
            return []
        rest = parts[3:]
        if not rest and any(re.match(r"(private|visibility)=", field) for field in fields):
            return [(OWNER_ONLY, {"what": "changes a repository's visibility"})]
        if rest[:1] == ["pages"]:
            return [(OWNER_ONLY, {"what": "changes a repository's Pages"})]
        if rest == ["releases"]:
            tag = next((field.split("=", 1)[1] for field in fields if field.startswith("tag_name=")), None)
            return [("gh-release", {"tag": tag})]
        if rest[:2] == ["actions", "workflows"] and rest[-1:] == ["dispatches"]:
            return [("workflow", {"workflow": "/".join(rest[2:-1])})]
        return []
    if positionals[:2] != ["release", "create"]:
        return []
    tag = positionals[2] if len(positionals) >= 3 else None
    return [("gh-release", {"tag": tag})]


def detect_git_tag_push(own: list[shell.Word]) -> list[tuple[str, dict]]:
    """Detect `git push` of `v*` tags (each refspec, `V` too, a glob, `--tags`, `--follow-tags` or
    `-c push.followTags=true`), excluding `--delete`, `-d`, `:tag` and `--dry-run`."""
    if name_of(own[0]) != "git":
        return []
    literals = [w.literal or "" for w in own[1:]]
    if any(lit in DISPLAY for lit in literals):
        return []
    index, follow = 0, False
    while index < len(literals) and literals[index].startswith("-"):
        if literals[index] == "-c" and index + 1 < len(literals):
            key, _, value = literals[index + 1].partition("=")
            follow = follow or (key.lower() == "push.followtags" and value.lower() not in ("false", "no", "off", "0"))
        index += 2 if literals[index] in GIT_OPTIONS_WITH_VALUE else 1
    if index >= len(literals) or literals[index] != "push":
        return []
    rest = literals[index + 1:]
    if has_help_or_dry_run(rest, allow_short_n=True):
        return []
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
        elif word in ("--tags", "--follow-tags"):
            all_tags = True
        elif word == "--no-follow-tags":
            follow = False
        elif not word.startswith("-"):
            positionals.append(word)
        pos += 1
    if delete:
        return []
    if all_tags or follow:
        return [("git-tag", {"tag": None})]
    refspecs = positionals[1:] if len(positionals) >= 2 else positionals
    hits = []
    for refspec in refspecs:
        clean = refspec.lstrip("+")
        if ":" in clean:
            source, _, dest = clean.partition(":")
            if not source:  # `:refs/tags/v1.0.0` deletes the remote tag
                continue
            target = dest
        else:
            target = clean
        if target.startswith("refs/tags/") and any(ch in target for ch in "*?["):
            hits.append(("git-tag", {"tag": None}))
            continue
        match = V_TAG_RE.match(target)
        if match:
            hits.append(("git-tag", {"tag": match.group(1)}))
    return hits


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

    if kind in ("publish", "release:publish", "workflow"):
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
        single = (detect_npm_access(own, raw_words)
                  or detect_package_publish(own, current)
                  or detect_release_script_or_repo_kit(own, current)
                  or detect_lanefather_ship(own, lane_cmds))
        hits = [single] if single else detect_gh_release(own) + detect_git_tag_push(own)
        for kind, details in hits:
            info = dict(details)
            info.setdefault("cwd", current)
            found.append((shell.show(own), kind, info))
    return found, self_assigned


# ---- standing permission ------------------------------------------------------------------------------------------

class Missing(Exception):
    """A fact the standing permission needs is missing; the message names it for the refusal and the card."""


# The repository-local settings that would point git at another repository or index; the hook's reads ignore them.
GIT_ENV_DROPPED = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR",
                   "GIT_NAMESPACE", "GIT_ALTERNATE_OBJECT_DIRECTORIES")


def git(cwd: str, *args: str, seconds: float = 2.0) -> str | None:
    """Output of a read-only git command in `cwd`, or None when it fails or the hook's time is spent."""
    env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_DROPPED}
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        proc = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, env=env,
                              timeout=hook_io.timeout(seconds), stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError, hook_io.OutOfTime):
        return None
    return proc.stdout if proc.returncode == 0 else None


def git_reader(cwd: str, commit: str):
    """`(read, listdir)` over the files of `commit`."""
    def read(path):
        return git(cwd, "show", f"{commit}:{path}")

    def listdir(path):
        out = git(cwd, "ls-tree", "-d", "--name-only", f"{commit}:{path}")
        return [line.strip() for line in (out or "").splitlines() if line.strip()]
    return read, listdir


def standing_shape(command: str, cwd: str | None) -> dict | None:
    """The one release command, in a form the projects' publishing docs use, that the standing permission may cover;
    None for anything else. Plain words only: no quoting, expansion, redirection, chaining, assignment (but the
    documented `<TOOL>_REVIEW_START=manual` before a promote) or option values written with `=`."""
    text = command.strip()
    if not SAFE_COMMAND_RE.fullmatch(text):
        return None
    words = text.split()
    prefix = words[0] if words and REVIEW_START_RE.fullmatch(words[0]) else None
    if prefix:
        words = words[1:]
    if not words or any("=" in word for word in words):
        return None
    if prefix is None and words == ["bun", "run", "release:publish"]:
        return {"kind": "release:publish"}
    if prefix is None and words == ["gh", "workflow", "run", "release-npm.yml", "--ref", "main"]:
        return {"kind": "workflow"}
    if prefix is None and len(words) == 5 and words[:4] == ["bun", "run", "release", "--"]:
        match = CUT_SPEC_RE.fullmatch(words[4])
        if match:
            return {"kind": "repo-kit-release", "pkg": match.group(1), "level": match.group(2)}
    if len(words) == 4 and words[1:2] == ["promote"] and words[3] == "--ship" and SHA_RE.fullmatch(words[2]):
        program = os.path.expanduser(words[0])
        lanes = lanefather_commands(cwd)
        if program.rsplit("/", 1)[-1] == "lanefather" or any(
                program == alias or program.endswith("/" + alias) or words[0] == alias for alias in lanes):
            return {"kind": "lanefather-ship", "sha": words[2]}
    return None


def remote_refs(root: str) -> tuple[str, dict[str, str]]:
    """`(sha of the remote's main, {tag: commit})` as `origin` reports them now: one network read."""
    out = git(root, "ls-remote", "origin", "refs/heads/main", "refs/tags/v*", "refs/tags/V*", seconds=REMOTE_SECONDS)
    if out is None:
        raise Missing("cannot read origin's main and tags (`git ls-remote origin` failed or timed out)")
    main, tags = None, {}
    for line in out.splitlines():
        sha, _, ref = line.partition("\t")
        if ref == "refs/heads/main":
            main = sha
        elif ref.startswith("refs/tags/"):
            name = ref[len("refs/tags/"):]
            if name.endswith("^{}"):
                tags[name[:-3]] = sha  # the peeled commit of an annotated tag wins
            else:
                tags.setdefault(name, sha)
    if not main:
        raise Missing("origin has no main branch")
    return main, tags


def standing(root: str, main: str) -> tuple[set[str], tuple[str, ...]]:
    """`(declared packages, allowed levels)` from `release_standing` in docs/agents/hooks.json of the remote's main."""
    if git(root, "cat-file", "-e", f"{main}^{{commit}}") is None:
        raise Missing(f"origin's main {main[:12]} is not in this clone: `git fetch origin` first")
    text = git(root, "show", f"{main}:{hook_io.PROJECT_FILE}")
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        data = {}
    declared = data.get(STANDING_KEY) if isinstance(data, dict) else None
    if not isinstance(declared, dict):
        raise Missing(f"the project gives no standing permission: no `{STANDING_KEY}` in {hook_io.PROJECT_FILE} on "
                      "origin's main")
    packages = set(hook_io.strings(declared.get("packages")))
    raw_levels = declared.get("levels", list(STANDING_LEVELS))
    levels = tuple(level for level in raw_levels if level in STANDING_LEVELS) if isinstance(raw_levels, list) else ()
    return packages, levels


def released_tags(root: str, commit: str, remote_tags: dict[str, str]) -> list[tuple[int, int, int]]:
    """Versions of the `v*` tags that exist on the remote, pointing where they point here, at ancestors of `commit`."""
    out = git(root, "for-each-ref", "--merged", commit, "--format=%(refname:short)%09%(objectname)%09%(*objectname)",
              "refs/tags")
    if out is None:
        raise Missing("cannot read the tags merged into the release commit")
    found = []
    for line in out.splitlines():
        name, _, rest = line.partition("\t")
        objectname, _, peeled = rest.partition("\t")
        version = semver(name)
        if version and remote_tags.get(name) in (peeled or objectname, objectname):
            found.append(version)
    return found


def semver(text: str | None) -> tuple[int, int, int] | None:
    match = SEMVER_RE.match(text or "")
    return tuple(int(part) for part in match.groups()) if match else None


def bump(version: tuple[int, int, int], level: str) -> tuple[int, int, int]:
    major, minor, patch = version
    return {"major": (major + 1, 0, 0), "minor": (major, minor + 1, 0), "patch": (major, minor, patch + 1)}[level]


def shown_version(version: tuple[int, int, int]) -> str:
    return ".".join(map(str, version))


def changelog_section(read, entry: dict, heading: str) -> str:
    """The CHANGELOG section headed `## <heading>` (`## [x.y.z](link)` too) of the package, else of the repository."""
    pattern = re.compile(rf"^##\s+\[?v?{re.escape(heading)}\]?(?:\([^)]*\))?(?:\s|$)", re.IGNORECASE)
    for path in dict.fromkeys((os.path.join(entry["dir"], "CHANGELOG.md"), "CHANGELOG.md")):
        lines = (read(path) or "").splitlines()
        for index, line in enumerate(lines):
            if pattern.match(line):
                end = next((j for j in range(index + 1, len(lines)) if re.match(r"##\s", lines[j])), len(lines))
                return "\n".join(lines[index + 1:end])
    raise Missing(f"no `## {heading}` section in the CHANGELOG of {entry['name']}")


def access_settings(read, listdir, entry_dir: str) -> tuple:
    """What decides a package's registry access in a commit: `publishConfig.access` and the kit configs' `access:`."""
    entries = [e for e in package_entries(read, listdir) if e["dir"] == entry_dir]
    config = entries[0]["data"].get("publishConfig") if entries else None
    access = config.get("access") if isinstance(config, dict) else None
    kits = tuple(tuple(re.findall(r"access\s*:\s*['\"](\w+)['\"]", read(name) or ""))
                 for name in ("package-kit.config.mjs", "repo-kit.config.mjs"))
    return access, kits


def standing_verdict(shape: dict, cwd: str | None) -> str:
    """`pkg@version (level)` when the standing permission covers `shape`, read from the commit and the remote;
    Missing naming the first fact that is not there."""
    if not cwd or git(cwd, "rev-parse", "--git-dir") is None:
        raise Missing("not inside a Git repository")
    root = (git(cwd, "rev-parse", "--show-toplevel") or "").strip()
    if os.path.realpath(root) != os.path.realpath(cwd):
        raise Missing(f"run it from the repository root, {root}")
    status = git(root, "status", "--porcelain", "--untracked-files=no")
    if status is None or status.strip():
        raise Missing("the checkout has uncommitted changes to tracked files")
    head = (git(root, "rev-parse", "HEAD") or "").strip()
    main, remote_tags = remote_refs(root)
    packages, levels = standing(root, main)
    kind = shape["kind"]
    if kind in ("release:publish", "workflow") and head != main:
        raise Missing(f"HEAD is not what origin's main points at ({main[:12]}): publish the commit on main")
    if kind == "lanefather-ship" and (git(root, "rev-parse", f"{shape['sha']}^{{commit}}") or "").strip() != head:
        raise Missing(f"{shape['sha']} is not this checkout's HEAD, so its versions cannot be read here")
    read, listdir = git_reader(root, head)
    publishable = [e for e in package_entries(read, listdir) if not e["private"]]
    if len(publishable) != 1:
        names = ", ".join(e["name"] for e in publishable) or "none"
        raise Missing(f"the standing permission covers one publishable package per repository; this one has "
                      f"{'more than one publishable package' if publishable else 'no publishable package'} ({names})")
    entry = publishable[0]
    name = entry["name"]
    if name not in packages:
        raise Missing(f"{name} is not declared under `{STANDING_KEY}` on origin's main")
    current = semver(entry["version"])
    if current is None:
        raise Missing(f"cannot read a plain x.y.z version for {name} ({entry['version'] or 'none'})")
    tags = released_tags(root, head, remote_tags)
    if not tags:
        raise Missing(f"no `v*` tag on origin before {name} {entry['version']}: a first publication of {name} is the "
                      "owner's call")
    previous = max(tags)
    if kind == "repo-kit-release":
        if shape["level"] == "major":
            raise Missing(f"{name} {shown_version(current)} -> major is a major step")
        target, heading = bump(current, shape["level"]), "Unreleased"
    else:
        target, heading = current, entry["version"]
    if kind == "lanefather-ship" and target == previous:
        return f"{name}@{shown_version(target)} (no new version)"
    if target <= previous:
        raise Missing(f"{name} {shown_version(target)} is not above the last released v{shown_version(previous)}")
    level = "major" if target[0] != previous[0] else "minor" if target[1] != previous[1] else "patch"
    if level not in levels:
        raise Missing(f"{name} {shown_version(previous)} -> {shown_version(target)} is a {level} step; the standing "
                      f"permission covers {' and '.join(levels) or 'no level'}")
    if BREAKING_RE.search(changelog_section(read, entry, heading)):
        raise Missing(f"the CHANGELOG section `## {heading}` of {name} has a Breaking entry: a breaking change is the "
                      "owner's call")
    before = git_reader(root, f"refs/tags/v{shown_version(previous)}")
    if access_settings(*before, entry["dir"]) != access_settings(read, listdir, entry["dir"]):
        raise Missing(f"{name}'s registry access changed since v{shown_version(previous)}: the owner's call")
    return f"{name}@{shown_version(target)} ({level})"


FOOTER = (f"Only the owner can grant it: set `{ENV_VAR}=<package>@<version>` in the environment before starting the "
          "release command (or `<version>` for a tag/GitHub release, `ship` for `lanefather promote --ship`), or "
          f"approve the permission card where the session shows one. Agents must never set `{ENV_VAR}` themselves; "
          "stop with the release ready and ask the owner, naming the fact above.")


def card_reaches_owner(data: dict) -> bool:
    """Whether a PreToolUse `ask` reaches a person here, never an automatic approval or a subagent no one watches."""
    return hook_io.card_reaches_owner(data)


def unreadable(command: str):
    """A command the shell reader cannot parse: refused when it names a release, passed otherwise."""
    if not RELEASE_WORDS_RE.search(re.sub(r"['\"\\]", "", command)):
        return None
    return hook_io.deny(
        "release-guard denied this command: it names a release, publish, visibility or access step and the guard "
        f"cannot read it. Run the release step on its own, as one plain command ({PLAIN_FORMS}).\n" + FOOTER)


def check(data: dict):
    command = hook_io.command_of(data)
    if command is None:
        return None
    cwd_raw = data.get("cwd")
    cwd = os.path.realpath(cwd_raw) if isinstance(cwd_raw, str) and cwd_raw else None
    try:
        found, self_assigned = actions(command, cwd)
    except (shell.Unreadable, ValueError, IndexError, StopIteration, RecursionError):
        return unreadable(command)
    if not found:
        return None
    env_value = os.environ.get(ENV_VAR, "").strip()
    tokens = [] if self_assigned else parse_tokens(env_value)
    pending = []
    for shown, kind, info in found:
        if kind == OWNER_ONLY:
            pending.append((shown, kind, f"it {info.get('what')}: that is the owner's command each time"))
        elif authorized(kind, info, tokens):
            hook_io.log("guard.log", f"release-guard ok={env_value!r} cwd={cwd} command={shown!r}")
        else:
            pending.append((shown, kind, None))
    if not pending:
        return None
    shape = standing_shape(command, cwd)
    if shape and len(found) == 1 and pending[0][1] == shape["kind"]:
        try:
            label = standing_verdict(shape, cwd)
        except Missing as missing:
            pending = [(pending[0][0], pending[0][1], str(missing))]
        except Exception as error:  # noqa: BLE001 - a classification bug refuses; it never lets a release through
            pending = [(pending[0][0], pending[0][1], f"the guard could not classify it ({error!r})")]
        else:
            hook_io.log("guard.log", f"release-guard standing {label} cwd={cwd} command={command!r}")
            return None
    blocked = [(shown, kind, fact or f"the standing permission covers only {PLAIN_FORMS}, run alone from the "
                                     "repository root") for shown, kind, fact in pending]
    lines = [f"- `{shown}`: {fact}" for shown, _, fact in dict.fromkeys(blocked)]
    owner_only = all(kind == OWNER_ONLY for _, kind, _ in blocked)
    if not self_assigned and card_reaches_owner(data):
        return hook_io.ask(
            "release-guard: the owner's approval is needed for this release or publish; approve only if you want it "
            "out now.\n" + "\n".join(lines))
    head = ("release-guard denied this command: registry versions, promoted releases and a repository's visibility "
            "cannot be unsent, and downstream repositories adopt releases automatically.\n" + "\n".join(lines))
    if owner_only:
        return hook_io.deny(head + "\nIt is the owner's command each time; no variable or standing permission covers "
                            "it. Stop and ask the owner to run it or to tell you to.")
    note = ""
    if self_assigned:
        note = (f"\nSetting `{ENV_VAR}` inside the command itself does not count: only the owner can grant it in the "
                "session environment before the command runs.")
    elif env_value:
        note = f"\n`{ENV_VAR}={env_value}` in the environment does not match what this command releases or publishes."
    return hook_io.deny(head + note + "\n" + FOOTER)


if __name__ == "__main__":
    sys.exit(hook_io.run("release-guard", check))
