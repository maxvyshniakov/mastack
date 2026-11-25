"""The friction journal: moments an agent misread or misused one of your packages, one JSON line each.

The format is repo-kit's friction schema (`repo-kit friction report` and `export` read it), taken from
`friction-contract.json` beside this file: a pinned copy of repo-kit's contract, changed only by copying repo-kit's
file and updating FRICTION_CONTRACT_SHA256. Its version, fields, kinds, limits, line encoding, session variables and
fingerprint rule are read from it; tests/friction_contract_test.py runs its golden cases against this writer.

    {"v": 1, "ts": ISO time, "project", "package", "kind", "component", "rule", "detail", "session", "source",
     "why", "file", "fingerprint"}

The file is `$FRICTION_JOURNAL`, else `$XDG_STATE_HOME/friction/events.jsonl` (`~/.local/state` without it);
`FRICTION_JOURNAL=off` turns every writer off. Everything stays on the machine.

Which packages count comes from `$MASTACK_CONFIG/friction.json` (default `~/.config/mastack/friction.json`):

    {
      "scopes": ["@scope/"],                          module prefixes whose type errors count
      "packages": {
        "@scope/ui-kit": {
          "aliases": ["UI Kit"],                      how people name it in prose (its last segment counts too)
          "types": ["~/ui-kit/dist/index.d.ts"]       declaration files whose exports are its component names
        }
      },
      "vendored": [ ... ]                             copies for `bin/friction vendor` (see there)
    }

Without the file, no package is configured, so package-specific events (type errors, scans, vendored patches)
are skipped; tool-level notes such as `large-bash-output` still record unless `FRICTION_JOURNAL=off`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path

import hook_io

CONTRACT_FILE = Path(__file__).resolve().with_name("friction-contract.json")
FRICTION_CONTRACT_SHA256 = "28da0c2c47b8cfb2a02bb2e9bc5081e9dfd1ba5d87446ca5b47afa5e4f331af6"
CONTRACT = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
_FIELDS = CONTRACT["schema"]["fields"]

SCHEMA = CONTRACT["schema"]["version"]
KINDS = tuple(CONTRACT["schema"]["kinds"])
FIELDS = tuple(field["name"] for field in _FIELDS)
DETAIL_LIMIT = CONTRACT["schema"]["limits"]["detail"]  # UTF-16 code units, as JavaScript counts a string
LINE_LIMIT = CONTRACT["schema"]["limits"]["line"]
SESSION_ENV = tuple(CONTRACT["build"]["session"]["env"])
_TS = re.compile(next(field for field in _FIELDS if field["name"] == "ts")["pattern"], re.ASCII)
_REQUIRED_TEXT = tuple(field["name"] for field in _FIELDS
                       if field["required"] and field["type"] == "string" and not field.get("format") and not field.get("oneOf"))
_STRING_FIELDS = tuple(field["name"] for field in _FIELDS if field["type"] == "string" and not field.get("format"))
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")
# The ISO 8601 shapes JavaScript's Date.parse takes for a time that starts like the contract's pattern, so this
# writer refuses no time repo-kit's reader keeps: 24:00 only as the end of a day, any day up to 31, z or Z,
# an offset with or without its colon, any number of fraction digits.
_JS_TIME = re.compile(r"\d{4}-(\d\d)-(\d\d)T(\d\d):(\d\d)(?::(\d\d)(?:\.(\d+))?)?(?:[Zz]|([+-])(\d\d):?(\d\d))?", re.ASCII)

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# tsc: `src/a.tsx(12,5): error TS2322: ...` and the pretty `src/a.tsx:12:5 - error TS2322: ...`.
TS_ERROR = re.compile(r"^[ \t]*(?P<file>[^\s:()'\"][^:()'\"]*?)(?:\((?P<line>\d+),\d+\)|:(?P<line2>\d+):\d+)"
                      r"[ \t]*:?[ \t]*(?:-[ \t]*)?error[ \t]+(?P<code>TS\d{4,5})[ \t]*:[ \t]*(?P<message>.+)$", re.M)
SPECIFIER = re.compile(r"['\"](@[\w.-]+/[\w.-]+)(/[\w./-]*)?['\"]")
EXPORT_MEMBER = re.compile(r"(?:no exported member(?: named)?|has no default export) '([\w$]+)'")
PASCAL = re.compile(r"\b([A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)*)\b")
SUFFIXES = ("Props", "Variants", "Variant", "Options", "Option", "Size", "State", "Config", "Type", "Element", "Ref")
IMPORT = re.compile(r"import\s+(?:type\s+)?([\w$\s{},*]+?)\s+from\s+['\"](@[\w.-]+/[\w.-]+)(?:/[^'\"]*)?['\"]")
EXPORTS = re.compile(r"export\s*\{([^}]*)\}|export\s+(?:declare\s+)?(?:function|const|class|let)\s+([A-Z][\w$]*)")


def journal_path(env=None) -> Path | None:
    env = os.environ if env is None else env
    if env.get("FRICTION_JOURNAL") == "off":
        return None
    if env.get("FRICTION_JOURNAL"):
        return Path(env["FRICTION_JOURNAL"]).expanduser()
    state = Path(env["XDG_STATE_HOME"]) if env.get("XDG_STATE_HOME") else Path.home() / ".local" / "state"
    return state / "friction" / "events.jsonl"


def config_dir(env=None) -> Path:
    import hook_io
    return hook_io.config_dir(env)


def load_config(env=None) -> dict:
    """The friction settings, {} when the file is missing or unreadable (fail open: then nothing is logged)."""
    try:
        data = json.loads((config_dir(env) / "friction.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def packages(config: dict) -> dict:
    found = config.get("packages")
    return {name: spec if isinstance(spec, dict) else {} for name, spec in found.items()} if isinstance(found, dict) else {}


def scopes(config: dict) -> list[str]:
    listed = [s for s in config.get("scopes", []) if isinstance(s, str) and s]
    return listed + [name for name in packages(config) if name not in listed]


def package_of(specifier: str, config: dict) -> str | None:
    """The configured package a module specifier belongs to: `@s/kit/icons` -> `@s/kit` when `@s/` is a scope."""
    if not specifier.startswith("@") or "/" not in specifier:
        return None
    name = "/".join(specifier.split("/")[:2])
    return name if any(name == scope or name.startswith(scope) for scope in scopes(config)) else None


def component_names(config: dict) -> dict[str, str]:
    """Exported PascalCase names of each configured package, from its declaration files: {name: package}."""
    names: dict[str, str] = {}
    for package, spec in packages(config).items():
        types = spec.get("types", [])
        for entry in [types] if isinstance(types, str) else types if isinstance(types, list) else []:
            try:
                text = Path(str(entry)).expanduser().read_text(encoding="utf-8")
            except OSError:
                continue
            for braces, single in EXPORTS.findall(text):
                for item in braces.split(",") if braces else [single]:
                    item = item.strip()
                    if not item or item.startswith("type "):
                        continue
                    name = item.split(" as ")[-1].strip()
                    if re.fullmatch(r"[A-Z][A-Za-z0-9]+", name):
                        names.setdefault(name, package)
    return names


def aliases(config: dict) -> dict[str, str]:
    """Prose names of each package, lowercased: {alias: package}."""
    found: dict[str, str] = {}
    for package, spec in packages(config).items():
        listed = spec.get("aliases", [])
        for alias in [package, package.split("/")[-1], *(listed if isinstance(listed, list) else [])]:
            if isinstance(alias, str) and len(alias) >= 3:
                found[alias.lower()] = package
    return found


def project_name(cwd) -> str:
    """The repository a directory belongs to, by name; a linked worktree names its main repository."""
    start = Path(cwd or ".").expanduser()
    for directory in [start, *start.parents]:
        git = directory / ".git"
        if git.is_file():
            match = re.search(r"^gitdir:\s*(.+)$", git.read_text(encoding="utf-8", errors="replace"), re.M)
            gitdir = (directory / match.group(1).strip()).resolve() if match else None
            text = str(gitdir) if gitdir else ""
            marker = f"{os.sep}.git{os.sep}worktrees{os.sep}"
            if marker in text:
                return Path(text.split(marker)[0]).name
            return directory.name
        if git.is_dir():
            return directory.name
    return start.name or "unknown"


def project_root(cwd) -> Path | None:
    start = Path(cwd or ".").expanduser()
    return next((d for d in [start, *start.parents] if (d / ".git").exists()), None)


def fingerprint(*parts) -> str:
    """The contract's key of a fact: sha256 of the parts as text joined by NUL, its first 16 hex digits."""
    rule = CONTRACT["fingerprint"]
    text = rule["separator"].join(str(p) for p in parts)
    return hashlib.new(rule["algorithm"], text.encode(rule["encoding"])).hexdigest()[:rule["length"]]


def _units(text: str) -> int:
    """Length in UTF-16 code units, as JavaScript counts a string: the unit of the contract's limits."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def _cut(text: str, units: int) -> str:
    """The first `units` UTF-16 code units; like JavaScript's slice it may leave half a surrogate pair."""
    return text.encode("utf-16-le", "surrogatepass")[:2 * units].decode("utf-16-le", "surrogatepass")


def session_id(env) -> str | None:
    return next((env[name] for name in SESSION_ENV if env.get(name)), None)


def build_event(fields: dict, *, cwd=None, env=None, now: datetime | None = None) -> dict:
    """An event by the contract's build rule: missing, null or empty fields are null, detail is a string cut to
    DETAIL_LIMIT, ts defaults to `now`, project to the repository of `cwd`, session to SESSION_ENV in `env`."""
    env = {} if env is None else env

    def text(value):
        return None if value is None or value == "" else str(value)

    ts = fields.get("ts")
    if ts is None:
        ts = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="milliseconds")
        ts = ts.replace("+00:00", "Z")
    project = text(fields.get("project"))
    if project is None and cwd is not None:
        project = project_name(cwd)
    session = text(fields.get("session"))
    return {"v": SCHEMA, "ts": ts, "project": project, "package": text(fields.get("package")) or "",
            "kind": fields.get("kind"), "component": text(fields.get("component")), "rule": text(fields.get("rule")),
            "detail": _cut(text(fields.get("detail")) or "", DETAIL_LIMIT),
            "session": session if session is not None else session_id(env), "source": text(fields.get("source")),
            "why": text(fields.get("why")), "file": text(fields.get("file")), "fingerprint": text(fields.get("fingerprint"))}


def event(*, package: str, kind: str, project: str, source: str, ts: str | None = None, component=None, rule=None,
          detail: str = "", session=None, why=None, file=None, fp=None) -> dict:
    return build_event({"ts": ts or None, "project": project, "package": package, "kind": kind, "component": component,
                        "rule": rule, "detail": detail, "session": session, "source": source, "why": why, "file": file,
                        "fingerprint": fp})


def _parses(ts: str) -> bool:
    """Whether JavaScript's Date.parse takes the time (held to the contract's edge-time cases)."""
    match = _JS_TIME.fullmatch(ts)
    if not match:
        return False
    month, day, hour, minute, second, fraction, sign, offset_hours, offset_minutes = match.groups()
    hour, minute, second = int(hour), int(minute), int(second or 0)
    if not (1 <= int(month) <= 12 and 1 <= int(day) <= 31 and minute <= 59 and second <= 59 and hour <= 24):
        return False
    if hour == 24 and (minute or second or int(fraction or 0)):
        return False
    return not sign or (int(offset_hours) <= 23 and int(offset_minutes) <= 59)


def problems(item) -> list[str]:
    """What makes an item no event of this schema, in the contract's order; [] for a valid one."""
    if not isinstance(item, dict):
        return ["an event is a JSON object"]
    found = []
    version = item.get("v")
    if isinstance(version, bool) or not isinstance(version, (int, float)) or version != SCHEMA:
        found.append(f"v must be {SCHEMA}")
    ts = item.get("ts")
    if not isinstance(ts, str) or not _TS.match(ts) or not _parses(ts):
        found.append("ts must be an ISO 8601 time")
    for field in _REQUIRED_TEXT:
        if not isinstance(item.get(field), str) or not item[field].strip():
            found.append(f"{field} is required")
    if item.get("kind") not in KINDS:
        found.append(f"kind must be one of {', '.join(KINDS)}")
    for field in _STRING_FIELDS:
        if item.get(field) is not None and not isinstance(item[field], str):
            found.append(f"{field} must be a string or null")
    if isinstance(item.get("detail"), str) and _units(item["detail"]) > DETAIL_LIMIT:
        found.append(f"detail is longer than {DETAIL_LIMIT} characters")
    return found


def _json(item: dict) -> str:
    """Compact JSON as JavaScript's JSON.stringify writes it: raw UTF-8, a lone surrogate as \\udxxx."""
    text = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
    return _LONE_SURROGATE.sub(lambda match: f"\\u{ord(match.group()):04x}", text)


def journal_event(item):
    """An event as the contract's write rule hands it to the journal: every field in FIELDS order (a missing one None),
    then the fields the schema does not name, and a string detail cut to DETAIL_LIMIT. A non-dict is left as is."""
    if not isinstance(item, dict):
        return item
    ready = {name: item.get(name) for name in FIELDS}
    ready.update((key, value) for key, value in item.items() if key not in ready)
    if isinstance(ready["detail"], str):
        ready["detail"] = _cut(ready["detail"], DETAIL_LIMIT)
    return ready


def line(item: dict) -> str:
    """The journal line of an event in schema order; when longer than LINE_LIMIT its detail loses the excess, once."""
    ready = journal_event(item)
    text = _json(ready)
    over = _units(text) - LINE_LIMIT
    if over <= 0 or not isinstance(ready["detail"], str):
        return text
    return _json({**ready, "detail": _cut(ready["detail"], max(0, _units(ready["detail"]) - over))})


def append(events: list[dict], env=None) -> int:
    """Append valid events, one line each in one write; returns how many. Never raises: an event with problems is
    left out and logged to the hooks' guard.log, an unwritable journal is silent."""
    path = journal_path(env)
    if not path:
        return 0
    good = []
    for item in map(journal_event, events):
        found = problems(item)
        if found:
            kind = item.get("kind") if isinstance(item, dict) else None
            hook_io.log("guard.log", f"friction journal refused a {kind} event: {'; '.join(found)}")
        else:
            good.append(item)
    if not good:
        return 0
    lines = [line(item) + "\n" for item in good]
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, "".join(lines).encode("utf-8"))
        finally:
            os.close(fd)
    except OSError:
        return 0
    return len(good)


def read(env=None) -> list[dict]:
    path = journal_path(env)
    if not path:
        return []
    found = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict) and item.get("v") == SCHEMA:
                    found.append(item)
    except OSError:
        pass
    return found


def _imports(path: Path, config: dict) -> dict[str, str]:
    """{imported name: package} for the configured packages a source file imports from."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:400_000]
    except OSError:
        return {}
    found: dict[str, str] = {}
    for clause, specifier in IMPORT.findall(text):
        package = package_of(specifier, config)
        if not package:
            continue
        for item in re.split(r"[\s,{}]+", clause.replace(" as ", " ")):
            if re.fullmatch(r"[A-Za-z_$][\w$]*", item) and item != "type":
                found[item] = package
    return found


def _base(name: str) -> str:
    for suffix in SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def type_errors(text: str, cwd, config: dict, *, session=None, source: str, ts: str | None = None,
                read_files: bool = True) -> list[dict]:
    """Events for the TypeScript errors in tool output that are about a configured package.

    An error counts when its message names a module under a configured scope, or names a type or component
    (`ButtonProps`, `CollapsibleTrigger`) that the erroring file imports from a configured package. Ordinary
    application type errors never count. Each event's `why` says which held."""
    if "error TS" not in text or not scopes(config):
        return []
    text = ANSI.sub("", text)
    project, root = project_name(cwd), project_root(cwd)
    events, seen = [], set()
    for match in TS_ERROR.finditer(text):
        code, message, file = match.group("code"), match.group("message").strip(), match.group("file").strip()
        tail = text[match.end():match.end() + 600].split("\n")[1:3]
        more = " ".join(line.strip() for line in tail if line.startswith((" ", "\t")) and "error TS" not in line)
        full = f"{message} {more}".strip()
        package = component = why = None
        for spec_match in SPECIFIER.finditer(full):
            package = package_of(spec_match.group(1), config)
            if package:
                member = EXPORT_MEMBER.search(full)
                component = member.group(1) if member else None
                why = f"the {code} message names {spec_match.group(1)}{spec_match.group(2) or ''}"
                break
        if not package and read_files:
            candidates = [Path(cwd or ".") / file] + ([root / file] if root else [])
            source_file = next((c for c in candidates if c.is_file()), None)
            imported = _imports(source_file, config) if source_file else {}
            for name in PASCAL.findall(full):
                for candidate in (name, _base(name)):
                    if candidate in imported:
                        package, component = imported[candidate], candidate
                        why = f"the {code} message names {name}; {file} imports {candidate} from {package}"
                        break
                if package:
                    break
        if not package:
            continue
        relative = file
        if root and Path(file).is_absolute():
            try:
                relative = str(Path(file).relative_to(root))
            except ValueError:
                relative = Path(file).name
        key = fingerprint(project, relative, code, re.sub(r"\d+", "N", message))
        if key in seen:
            continue
        seen.add(key)
        events.append(event(package=package, kind="type-error", project=project, source=source, ts=ts,
                            component=component, rule=code, detail=f"{code}: {full}", session=session, why=why,
                            file=relative, fp=key))
    return events


LARGE_OUTPUT_THRESHOLD = 8_000
_IDENTIFIER = re.compile(CONTRACT["redaction"]["identifier"]["pattern"], re.ASCII)
_SUBCOMMAND_TOOLS = frozenset({
    "git", "gh", "lanefather", "slotfather", "spawnfather", "junkfather",
    "bun", "npm", "pnpm", "yarn", "cargo", "docker", "kubectl", "repo-kit",
})
_SUBCOMMAND_VALUE_FLAGS = frozenset({
    "-C", "--git-dir", "--work-tree", "-c", "-R", "-n", "--namespace", "--context",
})
_WRAPPER_TOOLS = frozenset({"env", "nohup", "nice", "time", "command"})
_WRAPPER_VALUE_FLAGS = frozenset({"-u", "--unset", "-n", "--adjustment", "-C", "--chdir", "-P", "-S", "--split-string"})
_TIMEOUT_VALUE_FLAGS = frozenset({"-k", "--kill-after", "-s", "--signal"})
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_AUTH_HEADER_RE = re.compile(r"(?i)(\bAuthorization\s*:\s*)(?:(?:Bearer|Basic|Token)\s+)?[^\s'\";]+")
_BEARER_RE = re.compile(r"(?i)\b(Bearer\s+)[^\s'\";]+")
_ENV_SECRET_RE = re.compile(r"(?<![A-Za-z0-9_.-])([A-Za-z_][A-Za-z0-9_]*=)(?:\"[^\"]*\"|'[^']*'|[^\s;&|]+)")
_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]+|AKIA[0-9A-Z]{12,})"
)


def _safe_label(candidate: str, fallback: str = "bash") -> str:
    """Validate and cap a command label against the contract's identifier regex."""
    for value in (candidate, fallback):
        if value:
            capped = value[:80]
            if _IDENTIFIER.fullmatch(capped):
                return capped
    return "bash"


def _redact_command(cmd: str) -> str:
    """Redact inline secrets (env assignments, Authorization/Bearer headers, known token prefixes)."""
    text = _AUTH_HEADER_RE.sub(r"\1<redacted>", cmd)
    text = _BEARER_RE.sub(r"\1<redacted>", text)
    text = _ENV_SECRET_RE.sub(r"\1<redacted>", text)
    text = _TOKEN_RE.sub("<redacted>", text)
    return text


def command_label(command: str | None) -> str:
    """Short identifier of the command a Bash call ran (`git/diff`, `sed`, `lanefather/list`, ...)."""
    if not isinstance(command, str) or not command.strip():
        return "bash"
    # Skip leading `cd <dir> &&` / `;` prefix so the real command is named.
    segments = [seg.strip() for seg in re.split(r"\s*(?:&&|;)\s*", command.strip()) if seg.strip()]
    for segment in segments:
        first_line = segment.splitlines()[0].strip()
        try:
            tokens = shlex.split(first_line)
        except ValueError:
            tokens = first_line.split()
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if _ENV_ASSIGN.match(tok):
                i += 1
                continue
            base = os.path.basename(tok)
            if base in _WRAPPER_TOOLS:
                i += 1
                while i < len(tokens):
                    if tokens[i] == "--":
                        i += 1
                        break
                    if tokens[i] in _WRAPPER_VALUE_FLAGS:
                        i += 2
                        continue
                    if tokens[i].startswith("-"):
                        i += 1
                        continue
                    break
                continue
            if base == "timeout":
                i += 1
                while i < len(tokens):
                    if tokens[i] == "--":
                        i += 1
                        break
                    if tokens[i] in _TIMEOUT_VALUE_FLAGS:
                        i += 2
                        continue
                    if tokens[i].startswith("-"):
                        i += 1
                        continue
                    break
                if i < len(tokens):
                    i += 1  # duration
                continue
            break
        if i >= len(tokens):
            continue
        tool = os.path.basename(tokens[i])
        if tool == "cd" and len(segments) > 1:
            continue
        if tool in _SUBCOMMAND_TOOLS:
            j = i + 1
            while j < len(tokens):
                arg = tokens[j]
                if arg == "--":
                    break
                if arg in _SUBCOMMAND_VALUE_FLAGS:
                    j += 2
                    continue
                if arg.startswith("-") or _ENV_ASSIGN.match(arg):
                    j += 1
                    continue
                if "/" in arg or arg.startswith("."):
                    break
                return _safe_label(f"{tool}/{arg}", tool)
        return _safe_label(tool)
    return "bash"


def large_bash_output(text: str, command: str | None, cwd, *, session=None, source: str, ts: str | None = None,
                      threshold: int = LARGE_OUTPUT_THRESHOLD, size: int | None = None) -> dict | None:
    """A friction note when a Bash tool result exceeds `threshold` characters, naming the command."""
    if not isinstance(text, str):
        return None
    actual_size = len(text) if size is None else size
    if actual_size <= threshold:
        return None
    project = project_name(cwd)
    cmd = command.strip() if isinstance(command, str) else ""
    label = command_label(cmd)
    redacted = _redact_command(cmd)
    snippet = " ".join(redacted.split())[:200]
    detail = f"{actual_size} chars: {snippet}" if snippet else f"{actual_size} chars"
    why = f"Bash tool output was {actual_size} characters (over {threshold})"
    key = fingerprint(project, "large-bash-output", label, snippet)
    return event(package="mastack", kind="note", project=project, source=source, ts=ts, component=label,
                 rule="large-bash-output", detail=detail, session=session, why=why, fp=key)
