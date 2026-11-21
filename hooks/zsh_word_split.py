#!/usr/bin/env python3
"""zsh word-split guard, a Claude Code PreToolUse[Bash] check.

The Bash tool runs commands with zsh, which leaves an unquoted scalar $var whole
where bash and sh split it into words. Denies the shapes where that silently
changes what runs (2026-10-24: `set -- $pair` set one parameter, so three
checks never ran):

  set-scalar   `set [options] [--] ... $var ...`: one positional parameter, not one per word
  for-scalar   `for x in $var`, or a for list holding a $var the same command
               assigned a spaced value: one iteration over the whole string
  args-scalar  `cmd ... $var` where the same command assigned var an option string
               ("--quiet --no-color", or a loop word "-l -a"): cmd gets one argument

$var is a named parameter, $var or ${var}, unquoted and not known to be an array
(name=(...), typeset/declare/local -a, read -A, set -A, or one of zsh's own arrays
such as path and argv) nor to hold one word (x=abc, a loop over plain words, a
field of read other than its last). Text in quotes, comments and heredoc bodies is not read,
so a `bash -c '...'` script or `bash <<EOF` passes; $(...) and `...` bodies are.
Once a command turns on sh_word_split (setopt, set -o) or emulates sh, ksh or bash,
the commands after it in the same shell pass. Misses
are preferred to false positives: a command this parser cannot read passes.
"""
from __future__ import annotations

import re
import sys

import hook_io
import shell
from shell import Word

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\+?=")
OPTION = re.compile(r"^--?[A-Za-z]")
# zsh's own array parameters: an unquoted $path gives one word per element.
ZSH_ARRAYS = {"argv", "path", "fpath", "cdpath", "manpath", "mailpath", "module_path", "pipestatus", "match",
              "mbegin", "mend", "reply", "signals", "funcstack", "funcfiletrace", "funcsourcetrace", "functrace",
              "historywords", "precmd_functions", "preexec_functions", "chpwd_functions", "zsh_eval_context"}
WRAPPERS = {"env", "command", "builtin", "nohup", "time", "sudo", "noglob", "nocorrect", "exec"}
DECLARERS = {"export", "local", "typeset", "declare", "readonly", "integer", "float"}
# Commands for which one word and its split words come out the same, or that split again themselves.
WHOLE_IS_FINE = {"echo", "print", "eval", "[", "[[", "test", "case", ":", "unset"}


def assignment_of(word: Word) -> str | None:
    match = ASSIGNMENT.match(word.raw)
    return match.group(1) if match else None


def value_of(word: Word) -> str:
    return word.text.split("=", 1)[1] if "=" in word.text else ""


class Guard:
    def __init__(self):
        self.arrays = set(ZSH_ARRAYS)
        self.values: dict[str, str] = {}  # name -> "single" | "spaced" | "options"; absent when unknown
        self.split = False  # sh_word_split is on: zsh splits like bash
        self.findings: list[tuple[str, str, str]] = []

    def snapshot(self):
        return set(self.arrays), dict(self.values), self.split

    def restore(self, saved):
        self.arrays, self.values, self.split = set(saved[0]), dict(saved[1]), saved[2]

    def deny(self, rule: str, name: str, words: list[Word], what: str):
        if self.split or any(f[0] == rule and f[1] == name for f in self.findings):
            return
        shown = shell.show(words)
        self.findings.append((rule, name, f"[{rule}] `{shown}`: {what} Fix: `${{={name}}}` splits it, or keep the "
                                          f"words in an array (`{name}=(a b)`, then `${name}`); "
                                          f"write \"${name}\" when one word is meant."))

    def scalar(self, name: str | None) -> bool:
        """A scalar that may hold several words."""
        return bool(name) and name not in self.arrays and self.values.get(name) != "single"

    def note(self, name: str, values: list[str] | None):
        """Record the scalar values a command gave name; None when they are unknown."""
        self.arrays.discard(name)
        kind = spacing(values) if values is not None else None
        if values is not None and not kind and not any("\0" in v for v in values):
            kind = "single"
        if kind:
            self.values[name] = kind
        else:
            self.values.pop(name, None)

    def assign(self, name: str, word: Word, array: bool = False):
        if array or word.array:
            self.arrays.add(name)
            self.values.pop(name, None)
        else:
            self.note(name, [value_of(word)])

    def check(self, command: str):
        """Check each command in order. $(...), `...`, <(...) and ( ... ) run in a subshell: what they
        assign or set does not reach the commands after them."""
        self.walk_list(shell.read(command))

    def walk_subs(self, words: list[Word]):
        for word in words:
            for sub in word.subs:
                saved = self.snapshot()
                self.walk_list(shell.read(sub))
                self.restore(saved)

    def walk_list(self, lst: list):
        for and_or, _ in lst:
            for pipeline, _ in and_or:
                for command in pipeline:
                    self.walk_command(command)

    def walk_command(self, command):
        kind = command[0]
        if kind == "simple":
            self.walk_subs(command[1])
            self.simple(command[1])
        elif kind == "group":
            self.walk_list(command[1])
        elif kind in ("subshell", "function"):
            saved = self.snapshot()
            self.walk_list(command[1])
            self.restore(saved)
        elif kind == "if":
            for condition, body in command[1]:
                self.walk_list(condition)
                self.walk_list(body)
            if command[2]:
                self.walk_list(command[2])
        elif kind == "loop":
            if len(command) > 3:
                self.walk_subs(command[3])
                self.loop(command[3])
            self.walk_list(command[1])
            self.walk_list(command[2])
        elif kind == "case":
            for body in command[1]:
                self.walk_list(body)

    def simple(self, words: list[Word]):
        prefix = 0
        while prefix < len(words) and assignment_of(words[prefix]):
            prefix += 1
        if prefix == len(words):
            for word in words:
                self.assign(assignment_of(word), word)
            return
        words = words[prefix:]
        while words and words[0].literal in WRAPPERS:
            words = words[1:]
            while words and (assignment_of(words[0]) or (words[0].literal or "").startswith("-")):
                words = words[1:]
        if not words:
            return
        name = words[0].literal
        flags = "".join((w.literal or "")[1:] for w in words[1:] if (w.literal or "").startswith(("-", "+")))
        if name in DECLARERS:
            for word in words[1:]:
                assigned = assignment_of(word)
                if assigned:
                    self.assign(assigned, word, array="a" in flags or "A" in flags)
                elif ("a" in flags or "A" in flags) and IDENTIFIER.match(word.literal or ""):
                    self.arrays.add(word.literal)
        elif name == "read":
            names = [w.literal for w in words[1:] if IDENTIFIER.match(w.literal or "")]
            for index, variable in enumerate(names):
                self.note(variable, ["x"] if index < len(names) - 1 else None)  # the last one takes the rest
            if "A" in flags:
                self.arrays.update(names)
        elif name == "set":
            self.set(words)
        elif name in ("setopt", "unsetopt"):
            for word in words[1:]:
                self.option(word.literal, name == "setopt")
        elif name == "emulate":
            mode = next((w.literal for w in words[1:] if not (w.literal or "-").startswith("-")), None)
            if mode in ("sh", "ksh", "bash", "zsh", "csh"):
                self.split = mode in ("sh", "ksh", "bash")
        elif name not in WHOLE_IS_FINE:
            for word in words:
                if self.scalar(word.param) and self.values.get(word.param) == "options":
                    self.deny("args-scalar", word.param, words, f"`{words[0].raw}` gets ${word.param} as one "
                                                                "argument, not the options it holds.")

    def loop(self, words: list[Word]):
        if len(words) < 3 or words[2].literal != "in" or not IDENTIFIER.match(words[1].literal or ""):
            return
        variable, items = words[1].literal, words[3:]
        for word in items:
            name = word.param
            if self.scalar(name) and (len(items) == 1 or name in self.values):
                self.deny("for-scalar", name, words, f"the loop runs once, over all of ${name}.")
        self.note(variable, [w.text for w in items])

    def option(self, name: str | None, on: bool):
        option = (name or "").lower().replace("_", "")
        if option.removeprefix("no") == "shwordsplit":
            self.split = on != option.startswith("no")

    def set(self, words: list[Word]):
        args = words[1:]
        for index, word in enumerate(args):
            if word.literal in ("-A", "+A") and index + 1 < len(args) and args[index + 1].literal:
                self.arrays.add(args[index + 1].literal)
            if word.literal in ("-o", "+o") and index + 1 < len(args):
                self.option(args[index + 1].literal, word.literal == "-o")
        for word in args:
            if self.scalar(word.param):
                self.deny("set-scalar", word.param, words, f"set gets ${word.param} as one positional parameter, "
                                                           "not one per word.")


def spacing(values: list[str]) -> str | None:
    """"options" when a value is several words, one of them an option; "spaced" when only several words."""
    kind = None
    for value in values:
        pieces = value.split()
        if len(pieces) >= 2:
            if any(OPTION.match(p) for p in pieces):
                return "options"
            kind = "spaced"
    return kind


def check(data: dict):
    command = hook_io.command_of(data)
    if command is None or "$" not in command:
        return None
    guard = Guard()
    try:
        guard.check(command)
    except (shell.Unreadable, ValueError, IndexError, StopIteration, RecursionError):
        return None
    if guard.findings:
        return hook_io.deny("zsh word-split denied this command: the Bash tool runs zsh, which does not split an "
                            "unquoted scalar $var into words as bash does.\n" +
                            "\n".join(f"- {text}" for _, _, text in guard.findings))
    return None


if __name__ == "__main__":
    sys.exit(hook_io.run("zsh-word-split", check))
