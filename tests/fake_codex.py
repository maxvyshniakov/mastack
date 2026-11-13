"""A stand-in for the Codex CLI, so no test reads the real quota or starts the real CLI.

`codex app-server` answers initialize and account/rateLimits/read as Codex does, with FAKE_CODEX_USED percent of
the weekly (10080-minute) window used and FAKE_CODEX_REACHED as rateLimitReachedType. FAKE_CODEX_MODE changes it:
`silent` exits without answering, `hang` never answers and ignores the end of its input, `error` answers with a
JSON-RPC error, `malformed` answers with a result that is not an object. FAKE_CODEX_RESETS_AT is the weekly window's
resetsAt. Every start appends its arguments to FAKE_CODEX_LOG and its pid to FAKE_CODEX_PIDS.

`install` puts a `codex` on PATH that runs this file: by exec, or with shim=True as the npm package's Node shim does,
a parent that starts the server as its child and does not take it down when it is killed.
"""
import json
import os
import pathlib
import sys
import time


def install(directory: pathlib.Path, shim: bool = False) -> pathlib.Path:
    """A `codex` in `directory` that runs this stand-in."""
    directory.mkdir(parents=True, exist_ok=True)
    codex = directory / "codex"
    run = f'"{sys.executable}" "{pathlib.Path(__file__).resolve()}" "$@"'
    codex.write_text(f"#!/bin/sh\n{run} <&0 &\nwait\n" if shim else f"#!/bin/sh\nexec {run}\n")
    codex.chmod(0o755)
    return codex


def environment(base: dict, directory: pathlib.Path | None, log: pathlib.Path, **extra: str) -> dict:
    """`base` without MASTACK_ and FAKE_CODEX_ settings, with the stand-in in `directory` (None: no codex) first on
    PATH and its log at `log`."""
    env = {k: v for k, v in base.items() if not k.startswith(("MASTACK_", "FAKE_CODEX_")) and k != "XDG_STATE_HOME"}
    env.update(PATH=f"{directory}:/usr/bin:/bin" if directory else "/usr/bin:/bin", FAKE_CODEX_LOG=str(log),
               FAKE_CODEX_PIDS=str(log) + ".pids", **extra)
    return env


def reads(log: pathlib.Path) -> int:
    """How many times the quota was asked for (`codex app-server` starts)."""
    return sum(json.loads(line)[:1] == ["app-server"] for line in log.read_text().splitlines()) if log.exists() else 0


def alive(log: pathlib.Path) -> list[int]:
    """The stand-in processes still running."""
    found = []
    for line in (pathlib.Path(str(log) + ".pids").read_text().split() if pathlib.Path(str(log) + ".pids").exists()
                 else []):
        try:
            os.kill(int(line), 0)
            found.append(int(line))
        except OSError:
            pass
    return found


def main(args: list[str]) -> None:
    log = os.environ.get("FAKE_CODEX_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(args) + "\n")
    pids = os.environ.get("FAKE_CODEX_PIDS")
    if pids:
        with open(pids, "a", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\n")
    if args[:1] != ["app-server"]:
        print(f"fake codex: {' '.join(args)}")
        return
    mode = os.environ.get("FAKE_CODEX_MODE", "ok")
    if mode == "silent":
        return
    for line in sys.stdin:
        message = json.loads(line)
        if "id" not in message:
            continue
        if mode == "hang":
            time.sleep(120)
        if message.get("method") == "account/rateLimits/read":
            if mode == "malformed":
                print(json.dumps({"id": message["id"], "result": "not an object"}), flush=True)
                continue
            if mode == "error":
                print(json.dumps({"id": message["id"], "error": {"code": -32600, "message": "not logged in"}}), flush=True)
                continue
            weekly = {"usedPercent": float(os.environ.get("FAKE_CODEX_USED", "27")), "windowDurationMins": 10080}
            if os.environ.get("FAKE_CODEX_RESETS_AT"):
                weekly["resetsAt"] = int(os.environ["FAKE_CODEX_RESETS_AT"])
            five_hours = {"usedPercent": 3.0, "windowDurationMins": 300}
            print(json.dumps({"id": message["id"], "result": {"rateLimits": {
                "limitId": "codex", "primary": five_hours, "secondary": weekly,
                "rateLimitReachedType": os.environ.get("FAKE_CODEX_REACHED") or None,
                "spendControlReached": False}}}), flush=True)
        else:
            print(json.dumps({"id": message["id"], "result": {}}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
