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

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\+?=")
OPTION = re.compile(r"^--?[A-Za-z]")
# zsh's own array parameters: an unquoted $path gives one word per element.
ZSH_ARRAYS = {"argv", "path", "fpath", "cdpath", "manpath", "mailpath", "module_path", "pipestatus", "match",
              "mbegin", "mend", "reply", "signals", "funcstack", "funcfiletrace", "funcsourcetrace", "functrace",
              "historywords", "precmd_functions", "preexec_functions", "chpwd_functions", "zsh_eval_context"}
RESERVED = {"do", "then", "else", "elif", "if", "while", "until", "{", "}", "!", "done", "fi", "esac", "coproc"}
WRAPPERS = {"env", "command", "builtin", "nohup", "time", "sudo", "noglob", "nocorrect", "exec"}
DECLARERS = {"export", "local", "typeset", "declare", "readonly", "integer", "float"}
# Commands for which one word and its split words come out the same, or that split again themselves.
WHOLE_IS_FINE = {"echo", "print", "eval", "[", "[[", "test", "case", ":", "unset"}
OPERATORS = (";;", ";&", ";|", "&&", "||", "|&", "&|", ";", "&", "|")


class Unreadable(Exception):
    pass


class Word:
    def __init__(self, start: int):
        self.start = start
        self.raw = ""
        self.text = ""        # literal characters; each expansion is "\0"
        self.parts: list[tuple[str, str | None]] = []  # ("lit", None) or ("param", name), unquoted ones only
        self.quoted = False
        self.array = False    # name=( ... )
        self.subs: list[str] = []

    @property
    def param(self) -> str | None:
        """The name when the whole word is one unquoted $name or ${name}."""
        if len(self.parts) == 1 and self.parts[0][0] == "param" and not self.quoted:
            return self.parts[0][1]
        return None

    @property
    def literal(self) -> str | None:
        return None if "\0" in self.text else self.text

    @property
    def assignment(self) -> str | None:
        match = ASSIGNMENT.match(self.raw)
        return match.group(1) if match else None

    @property
    def value(self) -> str:
        return self.text.split("=", 1)[1] if "=" in self.text else ""


def matching(s: str, i: int, close: str) -> int:
    """Index just past the `close` that ends the construct whose body starts at i (quotes and nesting respected)."""
    depth = 1
    opener = {")": "(", "}": "{"}[close]
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            end = s.find("'", i + 1)
            if end < 0:
                raise Unreadable
            i = end + 1
            continue
        if c == '"':
            i = double_quoted(s, i, Word(i))
            continue
        if c == "`":
            i = backtick(s, i, Word(i))
            continue
        if c == opener:
            depth += 1
        elif c == close:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise Unreadable


def backtick(s: str, i: int, word: Word) -> int:
    j = i + 1
    while j < len(s) and s[j] != "`":
        j += 2 if s[j] == "\\" else 1
    if j >= len(s):
        raise Unreadable
    word.subs.append(s[i + 1:j])
    return j + 1


def dollar(s: str, i: int, word: Word, quoted: bool) -> int:
    """Read the expansion at s[i] == "$" into word; return the index after it."""
    nxt = s[i + 1:i + 2]
    if s.startswith("$((", i):
        end = matching(s, i + 2, ")")
        word.text += "\0"
        return end
    if nxt == "(":
        end = matching(s, i + 2, ")")
        word.subs.append(s[i + 2:end - 1])
        word.text += "\0"
        return end
    if nxt == "{":
        end = matching(s, i + 2, "}")
        body = s[i + 2:end - 1]
        word.text += "\0"
        if not quoted:
            word.parts.append(("param", body) if IDENTIFIER.match(body) else ("other", None))
        return end
    if nxt == "'" and not quoted:
        end = s.find("'", i + 2)
        while end > 0 and s[end - 1] == "\\":
            end = s.find("'", end + 1)
        if end < 0:
            raise Unreadable
        word.text += s[i + 2:end]
        word.quoted = True
        return end + 1
    match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", s[i + 1:])
    if match:
        word.text += "\0"
        if not quoted:
            word.parts.append(("param", match.group(0)))
        return i + 1 + match.end()
    if nxt and nxt in "0123456789@*#?$!-":
        word.text += "\0"
        if not quoted:
            word.parts.append(("other", None))
        return i + 2
    word.text += "$"
    if not quoted:
        word.parts.append(("lit", None))
    return i + 1


def double_quoted(s: str, i: int, word: Word) -> int:
    word.quoted = True
    j = i + 1
    while j < len(s):
        c = s[j]
        if c == '"':
            return j + 1
        if c == "\\" and j + 1 < len(s):
            word.text += s[j + 1]
            j += 2
        elif c == "$":
            j = dollar(s, j, word, quoted=True)
        elif c == "`":
            j = backtick(s, j, word)
            word.text += "\0"
        else:
            word.text += c
            j += 1
    raise Unreadable


def tokens(s: str) -> list:
    """Words and operators of a zsh command line: Word, ("op", text) or ("redirect", text)."""
    result: list = []
    word: Word | None = None

    def end_word():
        nonlocal word
        if word is not None:
            word.raw = s[word.start:i]
            result.append(word)
            word = None

    def current() -> Word:
        nonlocal word
        if word is None:
            word = Word(i)
        return word

    i = 0
    while i < len(s):
        c = s[i]
        if c in " \t":
            end_word()
            i += 1
        elif c == "\n":
            end_word()
            result.append(("op", ";"))
            i += 1
        elif c == "\\":
            if s[i + 1:i + 2] == "\n":
                end_word()
            else:
                current().text += s[i + 1:i + 2]
                current().quoted = True
            i += 2
        elif c == "#" and word is None:
            end = s.find("\n", i)
            i = len(s) if end < 0 else end
        elif c == "'":
            end = s.find("'", i + 1)
            if end < 0:
                raise Unreadable
            current().text += s[i + 1:end]
            current().quoted = True
            i = end + 1
        elif c == '"':
            i = double_quoted(s, i, current())
        elif c == "`":
            w = current()
            i = backtick(s, i, w)
            w.text += "\0"
            w.parts.append(("other", None))
        elif c == "$":
            i = dollar(s, i, current(), quoted=False)
        elif c in "<>" and s[i + 1:i + 2] == "(":
            w = current()
            end = matching(s, i + 2, ")")
            w.subs.append(s[i + 2:end - 1])
            w.text += "\0"
            w.parts.append(("other", None))
            i = end
        elif c in "<>" or (c == "&" and s[i + 1:i + 2] == ">"):
            if word is not None and word.text.isdigit() and not word.quoted:
                word = None  # the fd number of 2>&1
            end_word()
            j = i + 1
            while j < len(s) and s[j] in "<>&|" and j - i < 3:
                j += 1
            result.append(("redirect", s[i:j]))
            i = j
        elif c in ";&|":
            end_word()
            op = next(o for o in OPERATORS if s.startswith(o, i))
            result.append(("op", op))
            i += len(op)
        elif c == "(" and word is not None and s[word.start:i].endswith("="):
            end = matching(s, i + 1, ")")
            for inner in tokens(s[i + 1:end - 1]):
                if isinstance(inner, Word):
                    word.subs.extend(inner.subs)
            word.array = True
            word.text += "\0"
            i = end
        elif c in "()":
            end_word()
            result.append(("op", c))
            i += 1
        else:
            current().text += c
            if not word.parts or word.parts[-1][0] != "lit":
                word.parts.append(("lit", None))
            i += 1
    end_word()
    return result


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
        shown = " ".join(w.raw for w in words)
        shown = shown if len(shown) <= 80 else shown[:77] + "..."
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
            self.note(name, [word.value])

    def check(self, command: str):
        """Check each simple command in order. $(...), `...`, <(...) and ( ... ) run in a subshell: what they
        assign or set does not reach the commands after them."""
        scopes, words, skip = [], [], False
        for item in tokens(command) + [("op", ";")]:
            if isinstance(item, Word):
                if not skip:
                    words.append(item)
                skip = False
                continue
            if item[0] == "redirect":
                skip = True
                continue
            if words:
                for word in words:
                    for sub in word.subs:
                        saved = self.snapshot()
                        self.check(sub)
                        self.restore(saved)
                self.simple(words)
                words = []
            if item[1] == "(":
                scopes.append(self.snapshot())
            elif item[1] == ")" and scopes:
                self.restore(scopes.pop())

    def simple(self, words: list[Word]):
        while words and words[0].literal in RESERVED:
            words = words[1:]
        prefix = 0
        while prefix < len(words) and words[prefix].assignment:
            prefix += 1
        if prefix == len(words):
            for word in words:
                self.assign(word.assignment, word)
            return
        words = words[prefix:]
        while words and words[0].literal in WRAPPERS:
            words = words[1:]
            while words and (words[0].assignment or (words[0].literal or "").startswith("-")):
                words = words[1:]
        if not words:
            return
        name = words[0].literal
        flags = "".join((w.literal or "")[1:] for w in words[1:] if (w.literal or "").startswith(("-", "+")))
        if name in DECLARERS:
            for word in words[1:]:
                if word.assignment:
                    self.assign(word.assignment, word, array="a" in flags or "A" in flags)
                elif ("a" in flags or "A" in flags) and IDENTIFIER.match(word.literal or ""):
                    self.arrays.add(word.literal)
        elif name == "read":
            names = [w.literal for w in words[1:] if IDENTIFIER.match(w.literal or "")]
            for index, variable in enumerate(names):
                self.note(variable, ["x"] if index < len(names) - 1 else None)  # the last one takes the rest
            if "A" in flags:
                self.arrays.update(names)
        elif name == "for":
            self.loop(words)
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
        guard.check(hook_io.strip_heredocs(command))
    except (Unreadable, ValueError, IndexError, StopIteration, RecursionError):
        return None
    if guard.findings:
        return hook_io.deny("zsh word-split denied this command: the Bash tool runs zsh, which does not split an "
                            "unquoted scalar $var into words as bash does.\n" +
                            "\n".join(f"- {text}" for _, _, text in guard.findings))
    return None


if __name__ == "__main__":
    sys.exit(hook_io.run("zsh-word-split", check))
