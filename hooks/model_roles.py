"""The role table (models.toml) evaluated: which model takes a role now. `bin/role` prints it; the codex_credits
check reads the review threshold and the fallback from it.

A role lists choices in order; the first whose conditions all hold wins:

    when.limit      {quota: percent}: at least that share of the quota is left
    when.not_family the choice's family differs from the implementer's (unknown family: not met)
    only_families   (on the role) choices of other families never qualify

Each quota a condition names is read once, live. A quota that cannot be read does not meet its condition, and the
reason says why. The one quota known is `codex_weekly`: `codex app-server`, initialize, initialized,
`account/rateLimits/read`, 100 minus `usedPercent` of the 10080-minute window. A `rateLimitReachedType` or a
reached spend control fails the condition too, since a run would then be billed to credits.

Every read is stored in `<state>/codex-limit.json` (hook_io.state_dir), so the hook can reuse a recent one.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import hook_io

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "models.toml"
WEEK_MINUTES = 10080
READ_TIMEOUT = 20.0          # seconds for `bin/role`; the hook passes what its budget leaves
FAILED_READ_SECONDS = 60     # a failed read is reused this long at most, whatever max_age asks
CACHE_FILE = "codex-limit.json"
CONDITIONS = {"limit", "not_family"}
UNKNOWN_FAMILY = "implementer family not given (pass --implementer-family)"


class TableError(Exception):
    """models.toml is missing, unreadable, or names something it does not define."""


@dataclass
class Quota:
    left: int | None = None      # percent left
    reached: str | None = None   # Codex says the limit is reached (rateLimitReachedType, spend control)
    error: str | None = None     # why it could not be read
    read_at: float = 0.0
    resets_at: float | None = None  # when the window starts over (epoch seconds), as Codex reports it


@dataclass
class Choice:
    model: str
    id: str
    family: str
    cli: str
    effort: str
    argv: dict
    note: str | None
    option: str = "effort"


# ---- the table ----------------------------------------------------------------------------------------------------

def table_path() -> Path:
    return Path(os.path.expanduser(os.environ.get("MASTACK_MODELS") or str(TABLE)))


def load(path: Path | None = None) -> dict:
    path = path or table_path()
    try:
        import tomllib
    except ImportError as error:  # Python before 3.11
        raise TableError(f"reading {path} needs Python 3.11 or later ({error})") from None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise TableError(f"cannot read {path}: {error.strerror or error}") from None
    except tomllib.TOMLDecodeError as error:
        raise TableError(f"{path} is not valid TOML: {error}") from None
    if not isinstance(data.get("models"), dict) or not isinstance(data.get("roles"), dict):
        raise TableError(f"{path} has no [models] or [roles]")
    return data


def role_of(table: dict, role: str) -> dict:
    entry = table["roles"].get(role)
    if not isinstance(entry, dict) or not isinstance(entry.get("choices"), list):
        raise TableError(f"no role `{role}` in the table; roles: {', '.join(sorted(table['roles']))}")
    return entry


def model_of(table: dict, name) -> dict:
    model = table["models"].get(name) if isinstance(name, str) else None
    if not isinstance(model, dict) or not all(isinstance(model.get(k), str) for k in ("id", "family", "cli")):
        raise TableError(f"the table names model `{name}`, which [models] does not define with id, family and cli")
    return model


def conditions(choice: dict) -> dict:
    when = choice.get("when") or {}
    if not isinstance(when, dict) or set(when) - CONDITIONS:
        raise TableError(f"unknown condition in {choice}: only {', '.join(sorted(CONDITIONS))} are defined")
    limits = when.get("limit") or {}
    if not isinstance(limits, dict) or not all(isinstance(v, (int, float)) for v in limits.values()):
        raise TableError(f"`when.limit` in {choice} must map quotas to percentages")
    return when


def commands(table: dict, model: dict, effort: str) -> dict:
    """Each headless command [cli.<cli>] gives, with {id} and {effort} filled."""
    cli = (table.get("cli") or {}).get(model["cli"]) or {}
    return {name: [str(arg).replace("{id}", model["id"]).replace("{effort}", effort) for arg in argv]
            for name, argv in cli.items() if isinstance(argv, list)}


def effort_option(table: dict, model: dict) -> str:
    """Provider-specific option name for effort/reasoning (e.g. effort, model_reasoning_effort, thought_level)."""
    cli = (table.get("cli") or {}).get(model["cli"]) or {}
    if isinstance(cli.get("option"), str) and cli["option"]:
        return cli["option"]
    provider = (table.get("providers") or {}).get(model["family"]) or {}
    if isinstance(provider.get("option"), str) and provider["option"]:
        return provider["option"]
    return "effort"


def provider_metadata(table: dict, family: str) -> dict:
    """Cache window and context-budget metadata for `family`, or an empty dict."""
    entry = (table.get("providers") or {}).get(family)
    return dict(entry) if isinstance(entry, dict) else {}


def codex_threshold(table: dict, role: str = "review") -> int | float | None:
    """The `codex_weekly` share the role's first Codex choice needs, or None when it has none."""
    for choice in role_of(table, role)["choices"]:
        if isinstance(choice, dict) and model_of(table, choice.get("model"))["cli"] == "codex":
            need = (conditions(choice).get("limit") or {}).get("codex_weekly")
            if need is not None:
                return need
    return None


# ---- deciding -----------------------------------------------------------------------------------------------------

def unmet(name: str, need, quota: Quota) -> str | None:
    """Why `name` does not have `need` percent left, or None when it does."""
    if quota.error is not None:
        return f"{name} unreadable ({quota.error}), needs {need:g}%"
    if quota.left is None or quota.left < need:
        return f"{name} {quota.left}% left, needs {need:g}%"
    if quota.reached:
        return f"{name} {quota.left}% left, but Codex reports {quota.reached}"
    return None


def resolve(table: dict, role: str, implementer_family: str | None = None, read=None,
            family: str | None = None, exclude_families: set[str] | list[str] | tuple[str, ...] | None = None):
    """(the winning Choice or None, [{model, reason}] for each choice skipped before it, {quota: Quota} read).

    `read(name) -> Quota` reads a quota; each is read at most once, and only when a choice still needs it."""
    read = read or read_quota
    entry = role_of(table, role)
    only = entry.get("only_families")
    excluded = set(exclude_families or ())
    quotas: dict[str, Quota] = {}
    skipped = []
    for choice in entry["choices"]:
        if not isinstance(choice, dict):
            raise TableError(f"a choice of `{role}` is not a table: {choice!r}")
        name = choice.get("model")
        model = model_of(table, name)
        when = conditions(choice)
        effort = str(choice.get("effort") or "medium")
        reason = None
        if isinstance(only, list) and model["family"] not in only:
            reason = f"the {role} role takes only {', '.join(only)}"
        elif family is not None and model["family"] != family:
            reason = f"family is {model['family']}, requested {family}"
        elif model["family"] in excluded:
            reason = f"family {model['family']} excluded"
        elif when.get("not_family") and implementer_family is None:
            reason = UNKNOWN_FAMILY
        elif when.get("not_family") and model["family"] == implementer_family:
            reason = f"same family as the implementer ({implementer_family})"
        else:
            for quota_name, need in (when.get("limit") or {}).items():
                if quota_name not in quotas:
                    quotas[quota_name] = read(quota_name)
                reason = unmet(quota_name, need, quotas[quota_name])
                if reason:
                    break
        if reason:
            skipped.append({"model": name, "reason": f"{name}: {reason}"})
            continue
        return (Choice(name, model["id"], model["family"], model["cli"], effort, commands(table, model, effort),
                       choice.get("note"), effort_option(table, model)), skipped, quotas)
    return None, skipped, quotas


def caution(skipped: list) -> str | None:
    """A warning when a choice was skipped only because the implementer's family is unknown: the winner's note
    (such as "same family as the implementer") may then not hold."""
    if any(entry["reason"].endswith(UNKNOWN_FAMILY) for entry in skipped):
        return f"{UNKNOWN_FAMILY}: choices that need another family were skipped, so a note about the family " \
               "may not apply"
    return None


def describe(role: str, choice: Choice | None, skipped: list) -> str:
    lines = []
    if choice:
        lines.append(f"{role}: {choice.model} ({choice.id}, {choice.family}), effort {choice.effort}")
        lines += [f"  {name}: {shlex.join(argv)}" for name, argv in choice.argv.items()]
        if choice.cli == "antigravity":
            lines.append(f'  delegate_task: target.model="{choice.id}", target.options.{choice.option}="{choice.effort}"')
        elif not choice.argv and choice.option:
            lines.append(f"  option: {choice.option}={choice.effort}")
        if choice.note:
            lines.append(f"  note: {choice.note}")
        if caution(skipped):
            lines.append(f"  caution: {caution(skipped)}")
    else:
        lines.append(f"{role}: no choice qualifies")
    if skipped:
        lines.append("skipped:")
        lines += [f"  {entry['reason']}" for entry in skipped]
    return "\n".join(lines)


def as_json(role: str, choice: Choice | None, skipped: list, quotas: dict) -> dict:
    answer = asdict(choice) if choice else {"error": "no choice qualifies"}
    return {"role": role, **answer, "caution": caution(skipped), "skipped": skipped,
            "quotas": {name: {k: v for k, v in asdict(q).items() if k != "read_at"} for name, q in quotas.items()}}


# ---- quotas -------------------------------------------------------------------------------------------------------

def read_quota(name: str, timeout: float = READ_TIMEOUT) -> Quota:
    if name == "codex_weekly":
        return codex_weekly(timeout=timeout)
    return Quota(error=f"no reader for the quota `{name}`")


def codex_cli() -> str | None:
    return os.environ.get("MASTACK_CODEX") or shutil.which("codex")


def codex_weekly(timeout: float = READ_TIMEOUT, max_age: float = 0) -> Quota:
    """The weekly Codex limit. With max_age, a stored read younger than that (a failed one: FAILED_READ_SECONDS at
    most) is reused; every new read is stored."""
    cache = hook_io.state_dir() / CACHE_FILE
    if max_age > 0:
        stored = hook_io.read_json(str(cache))
        try:
            quota = Quota(**{k: stored[k] for k in ("left", "reached", "error", "read_at")},
                          resets_at=stored.get("resets_at"))
            now = time.time()
            age = now - float(quota.read_at)
            reset = quota.resets_at is not None and now >= float(quota.resets_at)
            if 0 <= age < (min(max_age, FAILED_READ_SECONDS) if quota.error else max_age) and not reset:
                return quota
        except (KeyError, TypeError, ValueError):
            pass
    quota = read_codex_weekly(timeout)
    quota.read_at = time.time()
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        partial = cache.with_suffix(f".{os.getpid()}.tmp")
        partial.write_text(json.dumps(asdict(quota)), encoding="utf-8")
        partial.replace(cache)
    except OSError:
        pass
    return quota


def read_codex_weekly(timeout: float) -> Quota:
    codex = codex_cli()
    if not codex:
        return Quota(error="codex is not on PATH")
    try:
        # A session of its own, so the whole group can be stopped: the npm package's codex is a Node shim that
        # passes SIGKILL on to nothing, and a server left behind would hold the pipes open.
        child = subprocess.Popen([codex, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True, start_new_session=True)
    except OSError as error:
        return Quota(error=f"codex app-server did not start: {error.strerror or error}")
    answer: dict = {}

    def listen() -> None:
        for line in child.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict) and message.get("id") == 2:
                answer.update(message)
                return

    reader = threading.Thread(target=listen, daemon=True)
    reader.start()
    try:
        for message in ({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "mastack-role",
                                                                                    "version": "1"}}},
                        {"method": "initialized"}, {"id": 2, "method": "account/rateLimits/read"}):
            child.stdin.write(json.dumps(message) + "\n")
        child.stdin.flush()
        reader.join(timeout)
    except OSError:
        pass
    finally:
        stop(child)
        reader.join(1)
        try:
            child.stdin.close()
        except OSError:
            pass
        if not reader.is_alive():  # closing it under a reader that still waits would block on its lock
            child.stdout.close()
    if not answer:
        return Quota(error=f"codex app-server gave no rate limits within {timeout:g} s")
    if answer.get("error"):
        error = answer["error"]
        return Quota(error=f"codex app-server: {error.get('message', error) if isinstance(error, dict) else error}")
    result = answer.get("result")
    limits = result.get("rateLimits") if isinstance(result, dict) else None
    if not isinstance(limits, dict):
        return Quota(error=f"codex app-server gave an unexpected answer: {str(result)[:80]}")
    windows = [w for w in (limits.get("primary"), limits.get("secondary")) if isinstance(w, dict)]
    weekly = next((w for w in windows if w.get("windowDurationMins") == WEEK_MINUTES), None)
    used = (weekly or {}).get("usedPercent")
    if not isinstance(used, (int, float)):
        return Quota(error="codex app-server reported no weekly window")
    reached = limits.get("rateLimitReachedType") or ("spend control reached" if limits.get("spendControlReached")
                                                     else None)
    resets = weekly.get("resetsAt")
    return Quota(left=max(0, int(100 - used)), reached=reached if isinstance(reached, str) else None,
                 resets_at=float(resets) if isinstance(resets, (int, float)) else None)


def stop(child: subprocess.Popen) -> None:
    """End the server's process group: SIGTERM, which the shim passes on, then SIGKILL for what is left."""
    for sig, grace in ((signal.SIGTERM, 1.0), (signal.SIGKILL, 1.0)):
        try:
            os.killpg(child.pid, sig)
        except OSError:
            pass
        try:
            child.wait(grace)
        except subprocess.TimeoutExpired:
            continue
        try:
            os.killpg(child.pid, 0)
        except OSError:
            return  # the whole group is gone
