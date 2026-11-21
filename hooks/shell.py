"""Shell reader for the Bash checks: strips heredoc bodies, tokenizes a zsh command line, parses compound
commands, and unwraps leading assignments and wrapper programs.

Read like the shell does: quoted text, comments and heredoc bodies are data; $(...), `...`, <(...) and ( ... )
hold their own command text. Misses are preferred to false positives: a command this reader cannot parse raises
Unreadable, which the calling check treats as passing.
"""
from __future__ import annotations

import re

# A heredoc operator and its delimiter: <<EOF, <<-'EOF', << "EOF"; the caller rules out the here-string <<<.
HEREDOC = re.compile(r"<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^]]*\])?\+?=")
WRAPPERS = {"env", "command", "builtin", "nohup", "time", "sudo", "exec", "noglob", "nocorrect", "nice"}
OPERATORS = (";;", ";&", ";|", "&&", "||", "|&", "&|", "&!", ";", "&", "|")
CASE_ENDS = {";;", ";&", ";|"}


class Unreadable(Exception):
    pass


class Word:
    def __init__(self, raw: str, text: str, subs: list[str],
                 parts: list[tuple[str, str | None]] = (), quoted: bool = False, array: bool = False):
        self.raw = raw      # as written
        self.text = text    # quotes removed; each expansion is "\0"
        self.subs = subs    # bodies of $(...), `...`, <(...)
        self.parts = list(parts)  # ("lit", None), ("param", name) or ("other", None), unquoted ones only
        self.quoted = quoted      # any quote, escape or $'...' in this word
        self.array = array        # name=( ... )

    @property
    def literal(self) -> str | None:
        return None if "\0" in self.text else self.text

    @property
    def param(self) -> str | None:
        """The name when the whole word is one unquoted $name or ${name}."""
        if len(self.parts) == 1 and self.parts[0][0] == "param" and not self.quoted:
            return self.parts[0][1]
        return None


def strip_heredocs(command: str) -> str:
    """The command without heredoc bodies: their text is data for the receiving command, not shell.

    Only an unquoted, uncommented `<<` starts a heredoc, so `echo "<<EOF"` cannot hide the lines after it; inside
    `"$( ... )"` the text is unquoted again, as in `git commit -m "$(cat <<'EOF' ...)"`."""
    out: list[str] = []
    pending: list[tuple[bool, str]] = []
    stack: list[str] = []  # open contexts: ' and " quote, $( and ( do not
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        context = stack[-1] if stack else ""
        if context == "'":
            if c == "'":
                stack.pop()
            out.append(c)
            i += 1
        elif c == "\\":
            out.append(command[i:i + 2])
            i += 2
        elif command.startswith("$(", i) and context in ('"', "", "$(", "("):
            stack.append("$(")
            out.append("$(")
            i += 2
        elif context == '"':
            if c == '"':
                stack.pop()
            out.append(c)
            i += 1
        elif c in "'\"(":
            stack.append(c)
            out.append(c)
            i += 1
        elif c == ")":
            if stack:
                stack.pop()
            out.append(c)
            i += 1
        elif c == "#" and (i == 0 or command[i - 1] in " \t\n;&|("):
            end = command.find("\n", i)
            end = n if end < 0 else end
            out.append(command[i:end])
            i = end
        elif command.startswith("<<", i) and not command.startswith("<<<", i) and command[i - 1:i] != "<" \
                and (match := HEREDOC.match(command, i)):
            pending.append((match.group(1) == "-", match.group(3)))
            out.append(match.group(0))
            i = match.end()
        elif c == "\n" and pending:
            out.append(c)
            i += 1
            while pending and i < n:  # skip each body through its delimiter line
                end = command.find("\n", i)
                line = command[i:n if end < 0 else end]
                i = n if end < 0 else end + 1
                dash, tag = pending[0]
                if (line.lstrip("\t") if dash else line) == tag:
                    pending.pop(0)
        else:
            out.append(c)
            i += 1
    return "".join(out)


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


def dollar(s: str, i: int, text: list[str], subs: list[str],
           parts: list[tuple[str, str | None]] | None = None) -> int:
    if s.startswith("$((", i):
        text.append("\0")
        if parts is not None:
            parts.append(("other", None))
        return closing(s, i + 3, "(", ")") + 1
    if s.startswith("$(", i):
        end = closing(s, i + 2, "(", ")")
        subs.append(s[i + 2:end - 1])
        text.append("\0")
        if parts is not None:
            parts.append(("other", None))
        return end
    if s.startswith("${", i):
        end = closing(s, i + 2, "{", "}")
        text.append("\0")
        if parts is not None:
            body = s[i + 2:end - 1]
            parts.append(("param", body) if IDENTIFIER.match(body) else ("other", None))
        return end
    if s.startswith("$'", i):
        j = i + 2
        while j < len(s) and s[j] != "'":
            j += 2 if s[j] == "\\" else 1
        if j >= len(s):
            raise Unreadable
        text.append(s[i + 2:j])
        if parts is not None:
            parts.append(("other", None))
        return j + 1
    match = re.match(r"[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-]", s[i + 1:])
    if match:
        text.append("\0")
        if parts is not None:
            name = match.group(0)
            parts.append(("param", name) if IDENTIFIER.match(name) else ("other", None))
        return i + 1 + match.end()
    text.append("$")
    if parts is not None:
        parts.append(("lit", None))
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
    start, text, subs, parts, quoted, array = None, [], [], [], False, False

    def end_word(i):
        nonlocal start, text, subs, parts, quoted, array
        if start is not None:
            result.append(Word(s[start:i], "".join(text), subs, parts, quoted, array))
        start, text, subs, parts, quoted, array = None, [], [], [], False, False

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
                quoted = True
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
            quoted = True
            i = end
        elif c == '"':
            start = i if at_start else start
            quoted = True
            i = double(s, i, text, subs)
        elif c == "`":
            start = i if at_start else start
            i = backtick(s, i, subs)
            text.append("\0")
            parts.append(("other", None))
        elif c == "$":
            start = i if at_start else start
            if s.startswith("$'", i):
                quoted = True
            i = dollar(s, i, text, subs, parts)
        elif c in "<>" and s[i + 1:i + 2] == "(":
            start = i if at_start else start
            end = closing(s, i + 2, "(", ")")
            subs.append(s[i + 2:end - 1])
            text.append("\0")
            parts.append(("other", None))
            i = end
        elif c in "<>" or (c == "&" and s[i + 1:i + 2] == ">"):
            if start is not None and not quoted and "".join(text).isdigit():
                start, text, subs, parts, quoted, array = None, [], [], [], False, False  # the fd number of 2>&1
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
            array = True
            i = end
        elif c in "()":
            end_word(i)
            result.append(("op", c))
            i += 1
        else:
            start = i if at_start else start
            text.append(c)
            if not parts or parts[-1][0] != "lit":
                parts.append(("lit", None))
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
        header = [self.take()]
        while not self.word("do") and not self.word("{"):
            item = self.take()
            if isinstance(item, Word):
                header.append(item)
            elif isinstance(item, tuple) and item[0] == "op" and item[1] == "(":  # zsh: for x (a b)
                while not self.op(")"):
                    inner = self.take()
                    if isinstance(inner, Word):
                        header.append(inner)
                self.at += 1
        if self.word("{"):
            return ("loop", [], self.parse_brace(), header)
        self.expect_word("do")
        body = self.parse_list(words={"done"})
        self.expect_word("done")
        return ("loop", [], body, header)

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


def read(command: str) -> list:
    """Parse `command` after stripping heredoc bodies; raises Unreadable when it cannot be read."""
    return parse(strip_heredocs(command))


# ---- meaning --------------------------------------------------------------------------------------------------

def unwrap(words: list[Word]) -> list[Word]:
    """The command's own words: without leading assignments and wrappers such as env and nohup."""
    index = 0
    while index < len(words) and ASSIGNMENT.match(words[index].raw):
        index += 1
    while index < len(words) and (words[index].literal or "").rsplit("/", 1)[-1] in WRAPPERS:
        wrapper_at = index
        wrapper = (words[index].literal or "").rsplit("/", 1)[-1]
        index += 1
        while index < len(words):
            option = words[index].literal or ""
            if ASSIGNMENT.match(words[index].raw):
                index += 1
            elif option == "--":
                index += 1
                break
            elif wrapper == "env" and option in ("--help", "--version"):
                return []  # display, not execution
            elif (wrapper == "env" and option in ("-S", "--split-string")) or (
                    wrapper in ("command", "builtin") and option in ("-v", "-V")):
                # Don't execute the named words; the wrapper's own failure can still gate a later mutation.
                return words[wrapper_at:]
            elif wrapper == "env" and option in ("-u", "--unset", "-C", "--chdir"):
                index += 2
            elif option.startswith("-"):
                index += 1
            else:
                break
    return words[index:]


def show(words: list[Word]) -> str:
    text = " ".join(w.raw for w in words)
    return text if len(text) <= 80 else text[:77] + "..."


def program(word: Word) -> str:
    """The word as a path, with "$" for expansions: `$I/tools/lane` reads as `$/tools/lane`."""
    return word.text.replace("\0", "$")
