"""The friction journal: moments an agent misread or misused one of your packages, one JSON line each.

The format is repo-kit's friction schema, version 1 (`repo-kit friction report` and `export` read it):

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

Without the file, nothing is about a package and nothing is written.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
KINDS = ("lint-finding", "selector-reach-in", "type-error", "owner-correction", "misuse", "vendored-patch",
         "review-finding", "note")
FIELDS = ("v", "ts", "project", "package", "kind", "component", "rule", "detail", "session", "source", "why", "file",
          "fingerprint")
DETAIL_LIMIT = 500
LINE_LIMIT = 4000

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
    env = os.environ if env is None else env
    return Path(env.get("MASTACK_CONFIG") or Path.home() / ".config" / "mastack").expanduser()


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
    return hashlib.sha256("\0".join(str(p) for p in parts).encode()).hexdigest()[:16]


def event(*, package: str, kind: str, project: str, source: str, ts: str | None = None, component=None, rule=None,
          detail: str = "", session=None, why=None, file=None, fp=None) -> dict:
    return {"v": SCHEMA, "ts": ts or datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "project": project, "package": package, "kind": kind, "component": component or None, "rule": rule or None,
            "detail": (detail or "")[:DETAIL_LIMIT], "session": session or None, "source": source, "why": why or None,
            "file": file or None, "fingerprint": fp or None}


def problems(item: dict) -> list[str]:
    found = []
    if item.get("v") != SCHEMA:
        found.append(f"v must be {SCHEMA}")
    if not re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d", str(item.get("ts", ""))):
        found.append("ts must be an ISO 8601 time")
    for field in ("project", "package", "source"):
        if not isinstance(item.get(field), str) or not item[field].strip():
            found.append(f"{field} is required")
    if item.get("kind") not in KINDS:
        found.append(f"kind must be one of {', '.join(KINDS)}")
    if len(item.get("detail") or "") > DETAIL_LIMIT:
        found.append(f"detail is longer than {DETAIL_LIMIT} characters")
    return found


def append(events: list[dict], env=None) -> int:
    """Append valid events, one line each in one write; returns how many. Never raises: a journal problem is silent."""
    path = journal_path(env)
    good = [e for e in events if not problems(e)]
    if not path or not good:
        return 0
    lines = []
    for item in good:
        line = json.dumps(item, ensure_ascii=False)
        if len(line) > LINE_LIMIT:
            line = json.dumps({**item, "detail": item["detail"][:max(0, len(item["detail"]) - (len(line) - LINE_LIMIT))]},
                              ensure_ascii=False)
        lines.append(line + "\n")
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
