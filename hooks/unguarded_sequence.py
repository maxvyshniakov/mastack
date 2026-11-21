#!/usr/bin/env python3
"""Unguarded sequence guard, a Claude Code PreToolUse[Bash] check.

`;` and a newline run the next step whatever the last one returned. Twice a mutating step ran after a failed one
(2026-10-27: a deploy script after a refused promote; 2026-10-28: `git merge` in the integration worktree after
a failed lane command skipped the `cd`). Denies a mutating step that runs after an unguarded step.

A step is an and-or list (pipelines joined by && and ||). It is unguarded when `;`, a newline or the end of a
`{ }`, `if` or loop body follows it, a command in it may fail in a way that matters, and it does not end in
`|| exit`, `|| return`, `|| break` or `|| continue` (or a group ending in one); `|| true` is no guard. A failure
does not matter for commands that only read and print (SHOWS, read-only git and gh forms, sed without -i, find
without -delete or -exec), for SETTINGS builtins, and for assignments without a command substitution; it does
for cd, a captured `x=$(...)`, checks (VALIDATORS; a MATCHERS or git command that is quiet or whose status picks
the step after `&&` or `||`) and everything else. Under errexit (`set -e`, `set -o errexit`, `setopt err_exit`)
a step is unguarded only when a pipeline before its `&&` or `||` may fail, or a command before the last `|` of its
final pipeline may fail without pipefail: zsh and bash do not exit on those failures. An option turned off
anywhere (a branch, a loop, a function body) counts as off from there on.

Mutating steps (keep the list narrow): MUTATING_GIT (including `git -C <dir>`, not with --abort or --quit),
`git worktree remove`, MUTATING_GH, Lanefather state/ref operations (including global --config options and
wrappers declared in lanefather_commands), and the project's own steps: `mutating_steps` in the repository's
docs/agents/hooks.json (the session's worktree, else its main checkout) and in the machine's hooks.json. A step
is `PROGRAM [VERB] [--OPTION]...`: PROGRAM matches the command's path or its end after a `/` (`tools/lane`
matches `$I/tools/lane`), VERB its first argument, and any one OPTION one of the arguments after the verb
(`--mark` matches `--mark=x`). Project steps also count when run through bash or python3, not under `bash -n`.

Read like the shell does: quoted text, comments and heredoc bodies are data; $(...), `...`, <(...) and ( ... )
run their own lists, which start with the parent's state and whose own unguarded steps stay inside; if and while
conditions are guarded by their test, and a function body is checked on its own. A step after `&` does not
wait for it. Misses are preferred to false positives: a command this parser cannot read passes.
"""
from __future__ import annotations

import os
import re
import sys

import hook_io
import shell
from shell import Unreadable, Word, program, read, show, unwrap
from vocabulary import GIT_OPTIONS_WITH_VALUE, SHELLS

MUTATING_GIT = {"merge", "push", "reset", "checkout", "switch", "rebase", "commit", "cherry-pick", "revert"}
MUTATING_GH = {("pr", "merge"), ("issue", "close")}

INTERPRETERS = {"python3", "python"} | SHELLS
# Steps whose failure leaves nothing for a later step to trip over: they only read and print, or set options.
SHOWS = {"echo", "print", "printf", "true", ":", "sleep", "pwd", "ls", "cat", "head", "tail", "wc", "grep",
         "egrep", "fgrep", "rg", "awk", "sort", "uniq", "cut", "tr", "column", "jq", "diff", "comm", "stat", "du",
         "df", "file", "which", "type", "whence", "ps", "pgrep", "lsof", "uptime", "whoami", "hostname", "uname",
         "tree", "nl", "basename", "dirname", "realpath", "readlink", "shasum", "md5", "date"}
# Checks: their failure means a prerequisite does not hold. Tests and comparisons always; a matcher when it is
# quiet or its status picks the next step after `&&` or `||`; git reads with an exit-status option.
VALIDATORS = {"[", "[[", "test", "((", "cmp"}
MATCHERS = {"grep", "egrep", "fgrep", "rg", "diff"}
QUIET = {"--quiet", "--silent", "--brief"}
GIT_MATCHERS = {"diff", "merge-base", "grep", "rev-parse", "show-ref", "ls-files"}
GIT_CHECK_OPTIONS = {"--quiet", "--exit-code", "--check", "--is-ancestor", "--verify", "--exists", "--error-unmatch"}
OPTIONS = ("errexit", "pipefail")
SETTINGS = {"set", "setopt", "unsetopt", "emulate", "export", "local", "typeset", "declare", "readonly", "integer",
            "float", "unset", "trap", "shopt", "alias", "unalias"}
READ_ONLY_GIT = {"log", "status", "show", "diff", "rev-parse", "merge-base", "ls-files", "ls-tree", "describe",
                 "shortlog", "blame", "cat-file", "for-each-ref", "rev-list", "show-ref", "grep", "name-rev",
                 "check-ignore", "count-objects", "range-diff", "cherry", "whatchanged", "version", "help", "var"}
READ_ONLY_GIT_FORMS = {("worktree", ("list",)), ("stash", ("list",)), ("stash", ("show",)), ("remote", ("-v",)),
                       ("remote", ("get-url",)), ("remote", ("show",)), ("remote", ()),
                       ("worktree", ("unlock",)), ("worktree", ("prune",))}  # their failure does not matter
READ_ONLY_GH = {("pr", "view"), ("pr", "list"), ("pr", "checks"), ("pr", "diff"), ("pr", "status"),
                ("issue", "view"), ("issue", "list"), ("issue", "status"), ("run", "view"), ("run", "list"),
                ("repo", "view"), ("auth", "status")}
GH_API_WRITES = {"-X", "--method", "-f", "-F", "--field", "--raw-field", "--input"}


def project_steps(cwd: str | None) -> list[tuple[str, str | None, frozenset[str]]]:
    """The machine's and the project's mutating steps as (program, verb or None, options)."""
    entries = hook_io.strings(hook_io.config().get("mutating_steps"))
    entries += hook_io.strings(hook_io.project_config(cwd).get("mutating_steps"))
    steps = []
    for entry in entries:
        program, *rest = entry.split() or [""]
        if not program:
            continue
        verb = rest[0] if rest and not rest[0].startswith("-") else None
        options = frozenset(word for word in rest[1 if verb else 0:] if word.startswith("-"))
        steps.append((program, verb, options))
    return steps


def project_step(name: str, args: list[str], steps) -> bool:
    for program, verb, options in steps:
        if name != program and not name.endswith("/" + program):
            continue
        if verb is not None and (not args or args[0] != verb):
            continue
        if options and not any(a.split("=", 1)[0] in options for a in args[1 if verb is not None else 0:]):
            continue
        return True
    return False


def lanefather_commands(cwd: str | None) -> list[str]:
    """Project/machine wrapper paths that have Lanefather's command semantics."""
    return (hook_io.strings(hook_io.config().get("lanefather_commands"))
            + hook_io.strings(hook_io.project_config(cwd).get("lanefather_commands")))


def lanefather_args(args: list[str]) -> list[str]:
    """Strip the known global option and its value; help/version never execute a subcommand."""
    position = 0
    while position < len(args) and args[position].startswith("-"):
        option = args[position]
        if option == "--config":
            position += 2
        elif option.startswith("--config="):
            position += 1
        else:
            return []  # help/version or an unreadable global option
    remaining = args[position:]
    return [] if any(a in ("-h", "--help") for a in remaining) else remaining


def lanefather_mutating(name: str, args: list[str], steps) -> bool:
    args = lanefather_args(args)
    if not args:
        return False
    verb, rest = args[0], args[1:]
    options = {a.split("=", 1)[0] for a in rest}
    if verb in {"start", "adopt", "land", "promote", "sync", "done"}:
        return True
    if verb == "review":
        # Explicit review edits/registration and --overall (a background review plus its ticket) mutate state.
        return bool(options & {"--mark", "--fix-lane", "--overall", "--force-reason"})
    if verb == "next":
        return "--start" in options
    if verb == "gc":
        return "--dry-run" not in options
    if verb in {"show", "list", "capabilities"}:
        return False
    return project_step(name, args, steps)  # e.g. a project's explicitly declared mutating project-hook


def mutating(words: list[Word], steps=(), lane_commands=()) -> bool:
    words = unwrap(words)
    if not words:
        return False
    name = program(words[0])
    if name.rsplit("/", 1)[-1] in INTERPRETERS and len(words) > 1:
        rest = words[1:]
        while rest and (rest[0].literal or "").startswith("-"):
            if rest[0].literal in ("-c", "-n"):  # a quoted script, or only a syntax check
                return False
            rest = rest[2:] if rest[0].literal in ("-W", "-X") else rest[1:]
        return bool(rest) and mutating(rest, steps, lane_commands)
    if name.rsplit("/", 1)[-1] == "lanefather" or any(
            name == alias or name.endswith("/" + alias) for alias in lane_commands):
        return lanefather_mutating(name, [w.text.replace("\0", "$") for w in words[1:]], steps)
    args = [w.literal or "" for w in words[1:]]
    if name == "git" or name.endswith("/git"):
        position = 0
        while position < len(args) and args[position].startswith("-"):
            position += 2 if args[position] in GIT_OPTIONS_WITH_VALUE else 1
        verb, rest = (args[position], args[position + 1:]) if position < len(args) else ("", [])
        if "--abort" in rest or "--quit" in rest:  # undoes a merge, rebase or cherry-pick in progress
            return False
        return verb in MUTATING_GIT or (verb == "worktree" and rest[:1] == ["remove"])
    if name == "gh" or name.endswith("/gh"):
        verbs = [a for a in args if not a.startswith("-")][:2]
        if tuple(verbs) in MUTATING_GH:
            return True
    return project_step(name, args, steps)


def option_changes(words: list[Word]) -> dict[str, bool]:
    """The shell options (errexit, pipefail) the command turns on (True) or off (False)."""
    words = unwrap(words)
    if not words:
        return {}
    name, args = words[0].literal, [w.literal or "" for w in words[1:]]
    changes: dict[str, bool] = {}
    if name == "set":
        index = 0
        while index < len(args) and args[index] != "--" and args[index][:1] in ("-", "+"):
            arg, on = args[index], args[index].startswith("-")
            if re.match(r"^[-+][A-Za-z]+$", arg):
                if "e" in arg:
                    changes["errexit"] = on
                if arg.endswith("o") and index + 1 < len(args):  # -o name, -eo name, +o name
                    option = args[index + 1].lower().replace("_", "")
                    if option in OPTIONS:
                        changes[option] = on
                    index += 1
            index += 1
    elif name in ("setopt", "unsetopt"):
        for arg in args:
            option = arg.lower().replace("_", "")
            if option.removeprefix("no") in OPTIONS:
                changes[option.removeprefix("no")] = (name == "setopt") != option.startswith("no")
    return changes


def checks(name: str, args: list[str], condition: bool) -> bool:
    """The command tests something: a test or comparison, a quiet match, or a match whose status picks the next
    step after `&&` or `||`. Its failure means the check did not hold."""
    if name in VALIDATORS:
        return True
    if name in MATCHERS:
        return condition or any(a in QUIET or re.match(r"^-[A-Za-z]*q[A-Za-z]*$", a) for a in args)
    if name == "git":
        position = 0
        while position < len(args) and args[position].startswith("-"):
            position += 2 if args[position] in GIT_OPTIONS_WITH_VALUE else 1
        verb, rest = (args[position], args[position + 1:]) if position < len(args) else ("", [])
        return (verb in GIT_MATCHERS and condition) or any(a in GIT_CHECK_OPTIONS for a in rest)
    return False


def only_shows(name: str, args: list[str], condition: bool = False) -> bool:
    """The command only reads and prints, so its failure leaves nothing for a later step to trip over."""
    if checks(name, args, condition):
        return False
    if name in SHOWS:
        return True
    if name == "sed":
        return not any(a.startswith("-i") or a.startswith("--in-place") for a in args)
    if name == "find":
        return not any(a in ("-delete", "-exec", "-execdir", "-ok", "-okdir") for a in args)
    if name == "git":
        position = 0
        while position < len(args) and args[position].startswith("-"):
            position += 2 if args[position] in GIT_OPTIONS_WITH_VALUE else 1
        verb, rest = (args[position], args[position + 1:]) if position < len(args) else ("", [])
        return verb in READ_ONLY_GIT or (verb, tuple(rest[:1])) in READ_ONLY_GIT_FORMS or (
            verb == "branch" and (not rest or "--show-current" in rest or "--list" in rest)) or (
            verb == "config" and any(a.startswith("--get") or a in ("--list", "-l") for a in rest))
    if name == "gh":
        verbs = tuple(a for a in args if not a.startswith("-"))[:2]
        if verbs[:1] == ("api",):
            return not any(a.split("=", 1)[0] in GH_API_WRITES for a in args)
        return verbs in READ_ONLY_GH
    return False


def simple_may_fail(words: list[Word], condition: bool) -> bool:
    """The command may fail in a way that matters to later steps: it changes state, or checks something."""
    own = unwrap(words)
    if not own:  # only assignments: they fail with their command substitution, and leave the value empty
        return any(word.subs for word in words)
    name = own[0].literal
    if leaves(("simple", own)):
        return False
    if name in SETTINGS:
        return name in ("export", "local", "typeset", "declare", "readonly") and any(w.subs for w in own)
    return not only_shows(program(own[0]).rsplit("/", 1)[-1], [w.literal or "" for w in own[1:]], condition)


def may_fail(command, condition: bool = False) -> bool:
    """condition: the command's pipeline is followed by `&&` or `||`, so its status picks the next step."""
    kind = command[0]
    if kind == "simple":
        return simple_may_fail(command[1], condition)
    if kind in ("group", "subshell"):
        return list_may_fail(command[1])
    if kind == "if":
        return any(list_may_fail(body) for _, body in command[1]) or list_may_fail(command[2] or [])
    if kind == "loop":
        return list_may_fail(command[2])
    if kind == "case":
        return any(list_may_fail(body) for body in command[1])
    return False  # a function definition


def list_may_fail(lst: list) -> bool:
    return any(fails for and_or, _ in lst for *_, fails in failures(and_or))


def leaves(command) -> bool:
    """`exit`, `return`, `break` or `continue`, or a group whose last step is one: the steps after it do not run."""
    if command[0] == "simple":
        own = unwrap(command[1])
        return bool(own) and own[0].literal in ("exit", "return", "break", "continue")
    if command[0] == "group" and command[1]:
        last_and_or = command[1][-1][0]
        last_pipeline = last_and_or[-1][0]
        return leaves(last_pipeline[-1])
    return False


def guarded(and_or: list) -> bool:
    """Ends in `|| exit`, `|| return`, `|| break`, `|| continue` or a group ending in one. `|| true` is no guard:
    the steps after it run in whatever state the failure left."""
    if len(and_or) < 2 or and_or[-2][1] != "||" or len(and_or[-1][0]) != 1:
        return False
    return leaves(and_or[-1][0][0])


def ignores(pipeline: list) -> bool:
    """A lone `true` or `:`: as a `||` handler it says the status before it does not matter."""
    return len(pipeline) == 1 and pipeline[0][0] == "simple" and bool(unwrap(pipeline[0][1])) and \
        unwrap(pipeline[0][1])[0].literal in ("true", ":")


def failures(and_or: list):
    """(op, index in pipeline, pipeline length, may fail) for each command of the step. A pipeline's last command
    is a condition when its status picks the next step after `&&` or `||` (not `|| true`)."""
    for position, (pipeline, op) in enumerate(and_or):
        handler = and_or[position + 1][0] if position + 1 < len(and_or) else []
        condition = op == "&&" or (op == "||" and not ignores(handler))
        for index, command in enumerate(pipeline):
            yield op, index, len(pipeline), may_fail(command, condition and index == len(pipeline) - 1)


def unguarded(and_or: list, state: "State") -> bool:
    """A failure in the step may leave the shell going on to the next one."""
    if not state.errexit:
        return any(fails for *_, fails in failures(and_or))
    for op, index, length, fails in failures(and_or):
        if fails and op is not None:  # errexit ignores a failure before `&&` or `||`; a `||` handler swallows it
            return True
        if fails and not state.pipefail and index < length - 1:
            return True  # the pipeline's status is its last command's: errexit never sees the failure
    return False


def first_words(command) -> list[Word]:
    """The words of the first simple command in command, to name a compound step."""
    kind = command[0]
    if kind == "simple":
        return command[1]
    if kind in ("group", "subshell"):
        lists = [command[1]]
    elif kind == "if":
        lists = [part for clause in command[1] for part in clause]
    elif kind == "loop":
        lists = [command[2]]
    elif kind == "case":
        lists = command[1]
    else:
        lists = []
    for lst in lists:
        for and_or, _ in lst:
            for pipeline, _ in and_or:
                for inner in pipeline:
                    words = first_words(inner)
                    if words:
                        return words
    return []


def describe(and_or: list) -> str:
    """The step as written, compound commands by their first command: `cd $W && git fetch | tail -1`."""
    parts = []
    for pipeline, op in and_or:
        shown = [show(c[1]) if c[0] == "simple" else show(first_words(c)) + " ..." for c in pipeline]
        parts.append(" | ".join(shown) + (f" {op} " if op else ""))
    text = "".join(parts)
    return text if len(text) <= 80 else text[:77] + "..."


class State:
    def __init__(self, errexit=False, pipefail=False, after=None):
        self.errexit = errexit
        self.pipefail = pipefail
        self.after: str | None = after  # the latest unguarded step this shell went on after

    def copy(self) -> "State":
        return State(self.errexit, self.pipefail, self.after)

    def turned_off(self, others: list["State"]):
        """An option some branch or function body turned off counts as off from here: no path analysis."""
        for option in OPTIONS:
            if any(not getattr(other, option) for other in others):
                setattr(self, option, False)


class Guard:
    def __init__(self, steps=(), lane_commands=()):
        self.findings: list[tuple[str, str, bool]] = []
        self.steps = steps
        self.lane_commands = lane_commands

    def check_list(self, lst: list, state: State):
        for and_or, separator in lst:
            for pipeline, _ in and_or:
                for index, command in enumerate(pipeline):
                    # Every pipeline element but the last runs in a subshell.
                    self.check_command(command, state if index == len(pipeline) - 1 else state.copy())
            # After `&` the next step does not wait; after `exit` or `return` nothing in this list runs.
            if separator == "&" or guarded(and_or) or leaves(and_or[-1][0][-1]):
                continue
            if unguarded(and_or, state):
                state.after = describe(and_or)

    def check_command(self, command, state: State):
        kind = command[0]
        if kind == "simple":
            words = command[1]
            for word in words:
                for sub in word.subs:
                    self.check_list(read(sub), state.copy())
            if state.after and mutating(words, self.steps, self.lane_commands):
                finding = (show(unwrap(words)), state.after, state.errexit)
                if finding not in self.findings:
                    self.findings.append(finding)
            for option, on in option_changes(words).items():
                setattr(state, option, on)
        elif kind == "group":
            self.check_list(command[1], state)
        elif kind == "subshell":
            self.check_list(command[1], state.copy())
        elif kind == "function":
            body = State(state.errexit, state.pipefail)
            self.check_list(command[1], body)
            state.turned_off([body])  # it may be called before the steps after it
        else:
            if kind == "if":
                branches = [body for _, body in command[1]] + [command[2] or []]
                conditions = [condition for condition, _ in command[1]]
            elif kind == "loop":
                branches, conditions = [command[2]], [command[1]]
            else:
                branches, conditions = command[1], []
            visited = []
            for condition in conditions:  # a failed test selects a branch: it guards itself
                visited.append(state.copy())
                self.check_list(condition, visited[-1])
            after = state.after
            for body in branches:  # one of them runs: an unguarded step in any reaches the steps after
                visited.append(state.copy())
                self.check_list(body, visited[-1])
                if visited[-1].after != state.after:
                    after = visited[-1].after
            state.after = after
            state.turned_off(visited)


def message(findings: list[tuple[str, str, bool]]) -> str:
    if any(errexit for _, _, errexit in findings):
        rule = ("unguarded-sequence denied this command: a mutating step runs after a step that may fail, "
                "and set -e does not stop on a failure before `&&` or `||`, nor on one inside a pipeline without "
                "pipefail. Fix: join the steps with `&&`, end the earlier chain with `|| exit 1`, or add "
                "`set -o pipefail`.")
    else:
        rule = ("unguarded-sequence denied this command: a mutating step runs after a step that may fail, "
                "because `;` and newlines go on after a failure (`|| true` too). Fix: join the steps with `&&`, "
                "or start the command with `set -eo pipefail`.")
    return "\n".join([rule] + [f"- `{step}` runs even if `{earlier}` failed." for step, earlier, _ in findings])


def check(data: dict):
    command = hook_io.command_of(data)
    if command is None or not any(c in command for c in ";\n"):
        return None
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) and data.get("cwd") else os.getcwd()
    guard = Guard(project_steps(cwd), lanefather_commands(cwd))
    try:
        guard.check_list(read(command), State())
    except (Unreadable, ValueError, IndexError, StopIteration, RecursionError):
        return None
    if guard.findings:
        return hook_io.deny(message(guard.findings))
    return None


if __name__ == "__main__":
    sys.exit(hook_io.run("unguarded-sequence", check))
