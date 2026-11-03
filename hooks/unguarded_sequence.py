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
`git worktree remove`, MUTATING_GH, and the project's own steps: `mutating_steps` in the repository's
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

MUTATING_GIT = {"merge", "push", "reset", "checkout", "switch", "rebase", "commit", "cherry-pick", "revert"}
MUTATING_GH = {("pr", "merge"), ("issue", "close")}

GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
WRAPPERS = {"env", "command", "builtin", "nohup", "time", "sudo", "exec", "noglob", "nocorrect", "nice"}
INTERPRETERS = {"python3", "python", "bash", "sh", "zsh"}
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
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^]]*\])?\+?=")
OPERATORS = (";;", ";&", ";|", "&&", "||", "|&", "&|", "&!", ";", "&", "|")
SEPARATORS = {";", "\n", "&"}
CASE_ENDS = {";;", ";&", ";|"}


class Unreadable(Exception):
    pass


class Word:
    def __init__(self, raw: str, text: str, subs: list[str]):
        self.raw = raw      # as written
        self.text = text    # quotes removed; each expansion is "\0"
        self.subs = subs    # bodies of $(...), `...`, <(...)

    @property
    def literal(self) -> str | None:
        return None if "\0" in self.text else self.text


# ---- tokens ---------------------------------------------------------------------------------------------------

def closing(s: str, i: int, opener: str, close: str) -> int:
    """Index just past the `close` that ends a construct whose body starts at i (quotes and nesting respected)."""
    depth = 1
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            i = single(s, i)
            continue
        if c == '"':
            i = double(s, i, [], [])
            continue
        if c == "`":
            i = backtick(s, i, [])
            continue
        if c == opener:
            depth += 1
        elif c == close:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise Unreadable


def single(s: str, i: int) -> int:
    end = s.find("'", i + 1)
    if end < 0:
        raise Unreadable
    return end + 1


def backtick(s: str, i: int, subs: list[str]) -> int:
    j = i + 1
    while j < len(s) and s[j] != "`":
        j += 2 if s[j] == "\\" else 1
    if j >= len(s):
        raise Unreadable
    subs.append(s[i + 1:j])
    return j + 1


def dollar(s: str, i: int, text: list[str], subs: list[str]) -> int:
    if s.startswith("$((", i):
        text.append("\0")
        return closing(s, i + 3, "(", ")") + 1
    if s.startswith("$(", i):
        end = closing(s, i + 2, "(", ")")
        subs.append(s[i + 2:end - 1])
        text.append("\0")
        return end
    if s.startswith("${", i):
        text.append("\0")
        return closing(s, i + 2, "{", "}")
    if s.startswith("$'", i):
        j = i + 2
        while j < len(s) and s[j] != "'":
            j += 2 if s[j] == "\\" else 1
        if j >= len(s):
            raise Unreadable
        text.append(s[i + 2:j])
        return j + 1
    match = re.match(r"[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-]", s[i + 1:])
    if match:
        text.append("\0")
        return i + 1 + match.end()
    text.append("$")
    return i + 1


def double(s: str, i: int, text: list[str], subs: list[str]) -> int:
    j = i + 1
    while j < len(s):
        c = s[j]
        if c == '"':
            return j + 1
        if c == "\\" and j + 1 < len(s):
            text.append(s[j + 1])
            j += 2
        elif c == "$":
            j = dollar(s, j, text, subs)
        elif c == "`":
            j = backtick(s, j, subs)
            text.append("\0")
        else:
            text.append(c)
            j += 1
    raise Unreadable


def tokens(s: str) -> list:
    """Words, ("op", text) and ("redirect", text) of a zsh command line; a newline is the op "\\n"."""
    result: list = []
    start, text, subs = None, [], []

    def end_word(i):
        nonlocal start, text, subs
        if start is not None:
            result.append(Word(s[start:i], "".join(text), subs))
        start, text, subs = None, [], []

    i = 0
    while i < len(s):
        c = s[i]
        at_start = start is None
        if c in " \t":
            end_word(i)
            i += 1
        elif c == "\n":
            end_word(i)
            result.append(("op", "\n"))
            i += 1
        elif c == "\\":
            if s[i + 1:i + 2] == "\n":
                end_word(i)
            else:
                start = i if at_start else start
                text.append(s[i + 1:i + 2])
            i += 2
        elif c == "#" and at_start:
            end = s.find("\n", i)
            i = len(s) if end < 0 else end
        elif at_start and (s.startswith("[[ ", i) or s.startswith("[[\t", i)):
            end = test_end(s, i + 2)
            result.append(Word(s[i:end], "[[", []))
            i = end
        elif at_start and s.startswith("((", i):
            end = closing(s, i + 2, "(", ")")
            if s[end:end + 1] != ")":
                raise Unreadable
            result.append(Word(s[i:end + 1], "((", []))
            i = end + 1
        elif c == "'":
            start = i if at_start else start
            end = single(s, i)
            text.append(s[i + 1:end - 1])
            i = end
        elif c == '"':
            start = i if at_start else start
            i = double(s, i, text, subs)
        elif c == "`":
            start = i if at_start else start
            i = backtick(s, i, subs)
            text.append("\0")
        elif c == "$":
            start = i if at_start else start
            i = dollar(s, i, text, subs)
        elif c in "<>" and s[i + 1:i + 2] == "(":
            start = i if at_start else start
            end = closing(s, i + 2, "(", ")")
            subs.append(s[i + 2:end - 1])
            text.append("\0")
            i = end
        elif c in "<>" or (c == "&" and s[i + 1:i + 2] == ">"):
            if start is not None and "".join(text).isdigit():
                start, text, subs = None, [], []  # the fd number of 2>&1
            end_word(i)
            j = i + 1
            while j < len(s) and s[j] in "<>&|-" and j - i < 3:
                j += 1
            result.append(("redirect", s[i:j]))
            i = j
        elif c in ";&|":
            end_word(i)
            op = next(o for o in OPERATORS if s.startswith(o, i))
            result.append(("op", "&" if op in ("&|", "&!") else op))
            i += len(op)
        elif c == "(" and start is not None and "".join(text).endswith("="):
            end = closing(s, i + 1, "(", ")")  # name=( ... ): an array assignment
            for inner in tokens(s[i + 1:end - 1]):
                if isinstance(inner, Word):
                    subs.extend(inner.subs)
            text.append("\0")
            i = end
        elif c in "()":
            end_word(i)
            result.append(("op", c))
            i += 1
        else:
            start = i if at_start else start
            text.append(c)
            i += 1
    end_word(len(s))
    return result


def test_end(s: str, i: int) -> int:
    """Index just past the `]]` that closes the [[ test whose body starts at i."""
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
        elif c == "'":
            i = single(s, i)
        elif c == '"':
            i = double(s, i, [], [])
        elif c == "$":
            i = dollar(s, i, [], [])
        elif s.startswith("]]", i) and s[i - 1] in " \t":
            return i + 2
        else:
            i += 1
    raise Unreadable


# ---- syntax ---------------------------------------------------------------------------------------------------
# A list is [(and_or, separator)]; an and_or is [(pipeline, op)] with op "&&", "||" or None for the last; a
# pipeline is [command]; a command is ("simple", [Word]), ("group", list), ("subshell", list),
# ("if", [(condition, body)], else_body), ("loop", condition, body), ("case", [body]) or ("function", body).

class Parser:
    def __init__(self, items: list):
        self.items = items
        self.at = 0

    def peek(self):
        return self.items[self.at] if self.at < len(self.items) else None

    def word(self, value=None) -> bool:
        item = self.peek()
        return isinstance(item, Word) and (value is None or item.literal == value)

    def op(self, *values) -> bool:
        item = self.peek()
        return isinstance(item, tuple) and item[0] == "op" and item[1] in values

    def take(self):
        item = self.peek()
        if item is None:
            raise Unreadable
        self.at += 1
        return item

    def expect_word(self, value: str):
        if not self.word(value):
            raise Unreadable
        self.at += 1

    def expect_op(self, value: str):
        if not self.op(value):
            raise Unreadable
        self.at += 1

    def skip_separators(self):
        while self.op(";", "\n"):
            self.at += 1

    def stopped(self, words, ops) -> bool:
        item = self.peek()
        if item is None:
            return True
        if isinstance(item, Word):
            return item.literal in words
        return item[0] == "op" and item[1] in ops

    def parse_list(self, words=frozenset(), ops=frozenset()) -> list:
        result = []
        while True:
            self.skip_separators()
            if self.stopped(words, ops):
                return result
            and_or = self.parse_and_or()
            separator = None
            if self.op(";", "\n", "&"):
                separator = self.take()[1]
            elif not self.stopped(words, ops):
                raise Unreadable
            result.append((and_or, separator))

    def parse_and_or(self) -> list:
        result = []
        while True:
            pipeline = self.parse_pipeline()
            if self.op("&&", "||"):
                op = self.take()[1]
                while self.op("\n"):
                    self.at += 1
                result.append((pipeline, op))
            else:
                result.append((pipeline, None))
                return result

    def parse_pipeline(self) -> list:
        if self.word("!"):
            self.at += 1
        result = [self.parse_command()]
        while self.op("|", "|&"):
            self.at += 1
            while self.op("\n"):
                self.at += 1
            result.append(self.parse_command())
        return result

    def redirections(self):
        while isinstance(self.peek(), tuple) and self.peek()[0] == "redirect":
            self.at += 1
            if isinstance(self.peek(), Word):
                self.at += 1

    def parse_command(self):
        item = self.peek()
        if item is None:
            raise Unreadable
        if self.op("("):
            self.at += 1
            body = self.parse_list(ops={")"})
            self.expect_op(")")
            command = ("subshell", body)
        elif self.word("{"):
            command = ("group", self.parse_brace())
        elif self.word("if"):
            command = self.parse_if()
        elif self.word("while") or self.word("until"):
            self.at += 1
            condition = self.parse_list(words={"do"})
            self.expect_word("do")
            command = ("loop", condition, self.parse_list(words={"done"}))
            self.expect_word("done")
        elif self.word("for") or self.word("select") or self.word("foreach"):
            command = self.parse_for()
        elif self.word("case"):
            command = self.parse_case()
        elif self.word("function"):
            self.at += 2
            if self.op("("):
                self.at += 1
                self.expect_op(")")
            command = ("function", self.parse_function_body())
        elif isinstance(item, Word) and self.at + 2 < len(self.items) and self.items[self.at + 1] == ("op", "(") \
                and self.items[self.at + 2] == ("op", ")"):
            self.at += 3
            command = ("function", self.parse_function_body())
        else:
            return self.parse_simple()
        self.redirections()
        return command

    def parse_brace(self) -> list:
        self.expect_word("{")
        body = self.parse_list(words={"}"})
        self.expect_word("}")
        return body

    def parse_function_body(self) -> list:
        self.skip_separators()
        command = self.parse_command()
        return [([([command], None)], None)]

    def parse_if(self):
        self.expect_word("if")
        clauses, otherwise = [], None
        while True:
            condition = self.parse_list(words={"then"})
            self.expect_word("then")
            clauses.append((condition, self.parse_list(words={"elif", "else", "fi"})))
            if self.word("elif"):
                self.at += 1
                continue
            if self.word("else"):
                self.at += 1
                otherwise = self.parse_list(words={"fi"})
            self.expect_word("fi")
            return ("if", clauses, otherwise)

    def parse_for(self):
        self.at += 1
        while not self.word("do") and not self.word("{"):
            item = self.take()
            if isinstance(item, tuple) and item[0] == "op" and item[1] == "(":  # zsh: for x (a b)
                while not self.op(")"):
                    self.take()
                self.at += 1
        if self.word("{"):
            return ("loop", [], self.parse_brace())
        self.expect_word("do")
        body = self.parse_list(words={"done"})
        self.expect_word("done")
        return ("loop", [], body)

    def parse_case(self):
        self.at += 1
        self.take()
        self.skip_separators()
        self.expect_word("in")
        bodies = []
        while True:
            self.skip_separators()
            if self.word("esac"):
                self.at += 1
                return ("case", bodies)
            if self.op("("):
                self.at += 1
            while not self.op(")"):
                self.take()
            self.at += 1
            bodies.append(self.parse_list(words={"esac"}, ops=CASE_ENDS))
            if self.op(*CASE_ENDS):
                self.at += 1

    def parse_simple(self):
        words, redirected = [], False
        while True:
            item = self.peek()
            if isinstance(item, Word):
                words.append(item)
                self.at += 1
            elif isinstance(item, tuple) and item[0] == "redirect":
                self.redirections()
                redirected = True
            else:
                break
        if not words and not redirected:
            raise Unreadable
        return ("simple", words)


def parse(command: str) -> list:
    parser = Parser(tokens(command))
    result = parser.parse_list()
    if parser.peek() is not None:
        raise Unreadable
    return result


# ---- meaning --------------------------------------------------------------------------------------------------

def unwrap(words: list[Word]) -> list[Word]:
    """The command's own words: without leading assignments and wrappers such as env and nohup."""
    index = 0
    while index < len(words) and ASSIGNMENT.match(words[index].raw):
        index += 1
    while index < len(words) and words[index].literal in WRAPPERS:
        index += 1
        while index < len(words) and (ASSIGNMENT.match(words[index].raw) or (words[index].literal or "").startswith("-")):
            index += 1
    return words[index:]


def show(words: list[Word]) -> str:
    text = " ".join(w.raw for w in words)
    return text if len(text) <= 80 else text[:77] + "..."


def program(word: Word) -> str:
    """The word as a path, with "$" for expansions: `$I/tools/lane` reads as `$/tools/lane`."""
    return word.text.replace("\0", "$")


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


def mutating(words: list[Word], steps=()) -> bool:
    words = unwrap(words)
    if not words:
        return False
    name = program(words[0])
    if name.rsplit("/", 1)[-1] in INTERPRETERS and len(words) > 1:
        rest = words[1:]
        while rest and (rest[0].literal or "").startswith("-"):
            if rest[0].literal in ("-c", "-n"):  # a quoted script, or only a syntax check
                return False
            rest = rest[1:]
        return bool(rest) and mutating(rest, steps)
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
    def __init__(self, steps=()):
        self.findings: list[tuple[str, str, bool]] = []
        self.steps = steps

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
                    self.check_list(parse(hook_io.strip_heredocs(sub)), state.copy())
            if state.after and mutating(words, self.steps):
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
    guard = Guard(project_steps(cwd))
    try:
        guard.check_list(parse(hook_io.strip_heredocs(command)), State())
    except (Unreadable, ValueError, IndexError, StopIteration, RecursionError):
        return None
    if guard.findings:
        return hook_io.deny(message(guard.findings))
    return None


if __name__ == "__main__":
    sys.exit(hook_io.run("unguarded-sequence", check))
