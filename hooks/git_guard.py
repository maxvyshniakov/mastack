#!/usr/bin/env python3
"""git-guard, a Claude Code PreToolUse[Bash] check.

Denies the git shapes behind incidents of parallel agents sharing one machine (audit 2026-10-21):
  pipe-mask        a mutating git step piped into tail/head/grep/sed/awk inside a
                   chain that continues with &&, || or ; and no `set -o pipefail`
  push-by-name     pushing main, dev or HEAD by name in a shared checkout's repository
                   (the `checkouts` setting) instead of `<sha>:refs/heads/<branch>`
  push-force       --force, --force-with-lease, +refspec or --no-verify on push
  shared-checkout  reset --hard, checkout -- <paths>, restore, clean -f in a
                   shared main checkout (its .claude/worktrees lanes are fine)
  stash            bare stash, a stash without -m <tag>, implicit pop/apply/drop, clear
  worktree-location git worktree add whose target path is outside
                   <repo>/.claude/worktrees/ and the session scratchpad (/tmp, $TMPDIR)

push-by-name applies in the shared checkouts and in every worktree of their repositories, found through
`git rev-parse --git-common-dir`; shared-checkout applies to the checkouts themselves, not to their
.claude/worktrees/; the other rules apply everywhere.

A command prefixed with GIT_GUARD_OK="<reason>" passes and is logged to
guard.log in the state directory; the override is the owner's, and deny messages do not offer it.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tempfile

import hook_io
import vocabulary
from vocabulary import GIT_OPTIONS_WITH_VALUE, SHELLS

MUTATING = {"merge", "push", "pull", "rebase", "cherry-pick", "commit", "am", "worktree"}
FILTERS = {"tail", "head", "grep", "sed", "awk"}
# Historically omits zsh-only wrappers and nice; kept explicit until the owner decides whether to align.
WRAPPERS = vocabulary.WRAPPERS - {"noglob", "nocorrect", "nice"}
PUNCTUATION = set("();<>|&")
PUSH_OPTIONS_WITH_VALUE = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
WORKTREE_ADD_OPTIONS_WITH_VALUE = {"-b", "-B", "--orphan", "--reason"}
SHA = re.compile(r"^[0-9a-f]{7,40}$")

SAFE = {
    "pipe-mask": "begin the command with `set -o pipefail;`, or run the git step alone and check its exit status "
                 "before the next step.",
    "push-by-name": "push the verified commit by SHA: `git push {remote} <sha>:refs/heads/<branch>`.",
    "push-force": "push a new commit on top, by SHA. Force pushes and skipped hooks are the owner's to run.",
    "shared-checkout": "run it in your own worktree under {repo}/.claude/worktrees/, or set work aside with a WIP commit.",
    "stash": "make a WIP commit, or `git stash push -u -m <unique-tag>`, then `git stash apply <sha>` and drop "
             "your entry by its tag.",
    "worktree-location": "put the worktree under {repo}/.claude/worktrees/<name> (or in the session scratchpad / "
                         "$TMPDIR), and wrap it with `junkfather own --kind worktree -- git worktree add ...` so it "
                         "has an owner.",
}


def segments(command: str):
    """Split a shell command into simple commands, each with the separator that follows it."""
    text = hook_io.strip_heredocs(command).replace("\\\n", " ")
    text = re.sub(r"(?<![\w$])\d+(?=[<>])", " ", text)  # the fd number of 2>&1, 2>/dev/null
    lexer = shlex.shlex(text.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    tokens = list(lexer)
    result, words, skip_target = [], [], False
    for token in tokens:
        if token and set(token) <= PUNCTUATION:
            if "<" in token or ">" in token:  # a redirection: its target is no argument
                skip_target = True
                continue
            kind = "chain" if any(op in token for op in ("&&", "||", ";")) else "pipe" if "|" in token else (
                "chain" if "&" in token else "group")
            result.append((words, kind))
            words = []
            continue
        if skip_target:
            skip_target = False
            continue
        words.append(token)
    result.append((words, "end"))
    return [(w, k) for w, k in result if w or k != "group"]


def unwrap(words):
    """Drop leading assignments and wrappers; return (assignments, words)."""
    assignments = {}
    index = 0
    while index < len(words):
        word = words[index]
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", word, re.S)
        if match:
            assignments[match.group(1)] = match.group(2)
        elif word in WRAPPERS:
            pass
        elif word.startswith("-") and index > 0 and words[index - 1] in WRAPPERS:
            pass
        else:
            break
        index += 1
    return assignments, words[index:]


def resolve(current: str | None, path: str) -> str | None:
    home = os.path.expanduser("~")
    path = re.sub(r"^\$\{?HOME\}?", home, path)
    tmpdir = os.environ.get("TMPDIR") or tempfile.gettempdir()
    path = re.sub(r"^\$\{?TMPDIR\}?", tmpdir, path)
    path = os.path.expanduser(path)
    if "$" in path or "`" in path:
        return None
    if not os.path.isabs(path):
        if current is None:
            return None
        path = os.path.join(current, path)
    return os.path.realpath(path)


def repo_root(directory: str | None) -> str | None:
    """The main repository checkout for `directory` (following linked worktrees), or `directory` itself."""
    if directory is None:
        return None
    root = hook_io.worktree_root(directory)
    if root is not None:
        if os.path.isfile(os.path.join(root, ".git")):
            return hook_io.main_checkout(root) or root
        return root
    for configured in hook_io.repos():
        if directory == configured or directory.startswith(configured + "/"):
            return configured
    return directory


def scratch_roots() -> tuple[str, ...]:
    roots = ["/tmp", "/private/tmp", "/var/folders", "/private/var/folders", tempfile.gettempdir()]
    tmpdir = os.environ.get("TMPDIR")
    if tmpdir:
        roots.append(tmpdir)
    return tuple(dict.fromkeys(os.path.realpath(r).rstrip("/") for r in roots if r))


def allowed_worktree_target(target: str, repo: str | None) -> bool:
    if repo is not None and target.startswith(repo.rstrip("/") + "/.claude/worktrees/"):
        return True
    home = os.path.realpath(os.path.expanduser("~")).rstrip("/")
    if target == home or target.startswith(home + "/"):
        return False
    return any(target.startswith(root + "/") for root in scratch_roots())


def shared_checkout(directory: str | None) -> str | None:
    if directory is None:
        return None
    for repo in hook_io.repos():
        if (directory == repo or directory.startswith(repo + "/")) and not directory.startswith(repo + "/.claude/worktrees/"):
            return repo
    return None


def protected_repo(directory: str | None) -> bool:
    if directory is None:
        return False
    roots = hook_io.repos()
    if not roots:
        return False
    if any(directory == root or directory.startswith(root + "/") for root in roots):
        return True
    if not os.path.isdir(directory):
        return False
    try:
        common = subprocess.run(["git", "-C", directory, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, timeout=hook_io.timeout(2)).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(common) and os.path.realpath(os.path.dirname(common)) in roots


def short_flag(args, letter):
    return any(re.match(r"^-[a-zA-Z]+$", a) and letter in a for a in args)


class Guard:
    def __init__(self):
        self.violations: list[tuple[str, str]] = []

    def deny(self, rule, what, **values):
        entry = (rule, f"[{rule}] {what} Safe: {SAFE[rule].format(**values)}")
        if entry not in self.violations:
            self.violations.append(entry)

    def check(self, command: str, cwd: str | None):
        try:
            parts = segments(command)
        except ValueError:  # unbalanced quotes: the shell will refuse it anyway
            return
        current, pipefail = cwd, False
        for index, (raw, separator) in enumerate(parts):
            _, words = unwrap(raw)
            if not words:
                continue
            name = os.path.basename(words[0])
            if name == "set" and "pipefail" in words and not any(w.startswith("+") for w in words[1:]):
                pipefail = True
            elif name == "cd":
                current = resolve(current, words[1]) if len(words) > 1 else os.path.expanduser("~")
            elif name in SHELLS and "-c" in words[1:-1]:
                self.check(words[words.index("-c") + 1], current)
            elif name == "git":
                self.git(words[1:], current, parts, index, separator, pipefail)

    def git(self, args, directory, parts, index, separator, pipefail):
        position = 0
        while position < len(args) and args[position].startswith("-"):
            option = args[position]
            if option == "-C" and position + 1 < len(args):
                directory = resolve(directory, args[position + 1])
            elif option.startswith("--work-tree="):
                directory = resolve(directory, option.split("=", 1)[1])
            position += 2 if option in GIT_OPTIONS_WITH_VALUE else 1
        if position >= len(args):
            return
        verb, rest = args[position], args[position + 1:]
        if verb in MUTATING and separator == "pipe" and not pipefail:
            follower = unwrap(parts[index + 1][0])[1] if index + 1 < len(parts) else []
            later = any(kind == "chain" and position_ + 1 < len(parts) and parts[position_ + 1][0]
                        for position_, (_, kind) in enumerate(parts) if position_ > index)
            if follower and os.path.basename(follower[0]) in FILTERS and later:
                self.deny("pipe-mask", f"`git {verb}` is piped into `{follower[0]}` and the chain continues, so the "
                                       f"chain sees {follower[0]}'s exit status and runs on after a failed git step "
                                       "(once a failed fast-forward was followed by a push).")
        getattr(self, "verb_" + verb.replace("-", "_"), lambda *_: None)(rest, directory)

    def verb_push(self, rest, directory):
        for option in rest:
            if option in ("-f", "--force", "--force-if-includes", "--no-verify") or option.startswith("--force-with-lease") \
                    or (re.match(r"^-[a-zA-Z]+$", option) and "f" in option):
                self.deny("push-force", f"`git push {option}` rewrites a shared branch or skips its checks.")
        positionals, position, delete = [], 0, False
        while position < len(rest):
            word = rest[position]
            if word in PUSH_OPTIONS_WITH_VALUE:
                position += 2
                continue
            if word in ("-d", "--delete"):
                delete = True
            elif word in ("--all", "--mirror", "--branches") and protected_repo(directory):
                self.deny("push-by-name", f"`git push {word}` pushes every local branch as it stands.", remote="origin")
            elif not word.startswith("-"):
                positionals.append(word)
            position += 1
        remote, refspecs = (positionals[0], positionals[1:]) if positionals else ("origin", [])
        for refspec in refspecs:
            if refspec.startswith("+"):
                self.deny("push-force", f"`+{refspec[1:]}` force-pushes that ref.")
            source, _, destination = refspec.lstrip("+").partition(":")
            if not _:
                destination = source
            branch = destination.removeprefix("refs/heads/")
            by_name = refspec == "HEAD" or (branch in ("main", "dev") and (delete or not SHA.match(source)))
            if by_name and protected_repo(directory):
                self.deny("push-by-name", f"`git push {remote} {refspec}` pushes whatever the local ref points at, "
                                          "not the commit you verified.", remote=remote)

    def destructive(self, verb, rest, directory):
        repo = shared_checkout(directory)
        if repo:
            self.deny("shared-checkout", f"`git {verb} {' '.join(rest)}` discards uncommitted work in the shared "
                                         f"checkout {repo}, where other sessions keep theirs.", repo=repo)

    def verb_reset(self, rest, directory):
        if "--hard" in rest:
            self.destructive("reset", rest, directory)

    def verb_checkout(self, rest, directory):
        if "--" in rest or "." in rest or "-f" in rest or "--force" in rest:
            self.destructive("checkout", rest, directory)

    def verb_restore(self, rest, directory):
        staged_only = ("--staged" in rest or short_flag(rest, "S")) and not ("--worktree" in rest or short_flag(rest, "W"))
        if not staged_only:
            self.destructive("restore", rest, directory)

    def verb_clean(self, rest, directory):
        if "--force" in rest or short_flag(rest, "f"):
            self.destructive("clean", rest, directory)

    def verb_stash(self, rest, directory):
        explicit = bool(rest) and not rest[0].startswith("-")
        sub, options = (rest[0], rest[1:]) if explicit else ("push", rest)
        shown = "git stash " + " ".join(rest) if rest else "git stash"
        if sub == "push":
            message = any(o in ("-m", "--message") for o in options[:-1]) or any(
                o.startswith("--message=") or (o.startswith("-m") and len(o) > 2) for o in options)
            if not message:
                self.deny("stash", f"`{shown}` adds an untagged entry to the stash stack every worktree and session "
                                   "shares, so a later pop can take another session's work.")
        elif sub == "save" and not [o for o in options if not o.startswith("-")]:
            self.deny("stash", f"`{shown}` adds an untagged entry to the shared stash stack.")
        elif sub in ("pop", "apply", "drop") and not [o for o in options if not o.startswith("-")]:
            self.deny("stash", f"`{shown}` takes the top entry of the shared stash stack, which may be another "
                               "session's.")
        elif sub == "clear":
            self.deny("stash", f"`{shown}` deletes every session's stash entries.")

    def verb_worktree(self, rest, directory):
        if not rest or rest[0] != "add":
            return
        args = rest[1:]
        target_raw, position = None, 0
        while position < len(args):
            word = args[position]
            if word in ("-h", "--help"):
                return
            if word == "--":
                if position + 1 < len(args):
                    target_raw = args[position + 1]
                break
            if word in WORKTREE_ADD_OPTIONS_WITH_VALUE:
                position += 2
                continue
            if word.startswith("-"):
                position += 1
                continue
            target_raw = word
            break
        if not target_raw:
            return
        target = resolve(directory, target_raw)
        if target is None:
            return
        repo = repo_root(directory)
        if not allowed_worktree_target(target, repo):
            self.deny("worktree-location",
                      f"`git worktree add {target_raw}` places a worktree at `{target}`, outside "
                      f"`{repo or '<repo>'}/.claude/worktrees/` and the session scratchpad.",
                      repo=repo or "<repo>")


def check(data: dict):
    command = hook_io.command_of(data)
    if command is None or "git" not in command:
        return None
    cwd = data.get("cwd")
    try:
        first = segments(command)[0][0]
    except (ValueError, IndexError):
        first = []
    reason = unwrap(first)[0].get("GIT_GUARD_OK", "").strip()
    if reason:
        hook_io.log("guard.log", f"git-guard override reason={reason!r} cwd={cwd} command={command!r}")
        return None
    guard = Guard()
    guard.check(command, os.path.realpath(cwd) if isinstance(cwd, str) and cwd else None)
    if guard.violations:
        return hook_io.deny("git-guard denied this command.\n" + "\n".join(f"- {text}" for _, text in guard.violations))
    return None


if __name__ == "__main__":
    sys.exit(hook_io.run("git-guard", check))
