"""A stand-in for the Codex CLI, so no test reads the real quota or starts the real CLI.

`codex app-server` answers initialize and account/rateLimits/read as Codex does, with FAKE_CODEX_USED percent of
the weekly (10080-minute) window used and FAKE_CODEX_REACHED as rateLimitReachedType. FAKE_CODEX_MODE changes it:
`silent` exits without answering, `hang` never answers, `error` answers with a JSON-RPC error. Every start appends
its arguments to FAKE_CODEX_LOG. Tests put a `codex` on PATH that runs this file.
"""
import json
import os
import pathlib
import sys
import time


def install(directory: pathlib.Path) -> pathlib.Path:
    """A `codex` in `directory` that runs this stand-in."""
    directory.mkdir(parents=True, exist_ok=True)
    codex = directory / "codex"
    codex.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{pathlib.Path(__file__).resolve()}" "$@"\n')
    codex.chmod(0o755)
    return codex


def main(args: list[str]) -> None:
    log = os.environ.get("FAKE_CODEX_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(args) + "\n")
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
            time.sleep(60)
        if message.get("method") == "account/rateLimits/read":
            if mode == "error":
                print(json.dumps({"id": message["id"], "error": {"code": -32600, "message": "not logged in"}}), flush=True)
                continue
            weekly = {"usedPercent": float(os.environ.get("FAKE_CODEX_USED", "27")), "windowDurationMins": 10080}
            five_hours = {"usedPercent": 3.0, "windowDurationMins": 300}
            print(json.dumps({"id": message["id"], "result": {"rateLimits": {
                "limitId": "codex", "primary": five_hours, "secondary": weekly,
                "rateLimitReachedType": os.environ.get("FAKE_CODEX_REACHED") or None,
                "spendControlReached": False}}}), flush=True)
        else:
            print(json.dumps({"id": message["id"], "result": {}}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
