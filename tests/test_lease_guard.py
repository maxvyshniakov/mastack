#!/usr/bin/env python3
"""Tests for hooks/lease_guard.py with real processes."""
from __future__ import annotations

import json
import os
import pathlib
import pwd
import shutil
import subprocess
import sys
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from hook_test_support import HookCase, fixture  # noqa: E402

FAKE_STATUS = r'''#!/usr/bin/env python3
"""A stand-in for `slotfather status --json [--pid PID]` serving the leases in $FAKE_QUEUE, as slotfather does."""
import json, os, subprocess, sys
queue = json.load(open(os.environ["FAKE_QUEUE"]))
args = sys.argv[1:]
if args[:2] != ["status", "--json"]:
    sys.exit(2)
public = lambda entry: {k: v for k, v in entry.items() if k not in ("env", "start_override")}
out = {"v": 1, "slots": 4, "held": len(queue), "free": 0, "legacy": []}
if args[2:3] == ["--pid"]:
    pid = int(args[3])
    found, start = [], None
    for entry in queue:
        via = "tree" if pid in entry["tree"] else "env" if pid in entry.get("env", []) else None
        if via:
            found.append({**public(entry), "via": via})
            start = entry.get("start_override") or start
    if start is None:
        ps = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                            env={**os.environ, "LC_ALL": "C"}).stdout.strip()
        start = ps or None
    out.update(entries=found, query={"pid": pid, "start": start})
else:
    out["entries"] = [public(entry) for entry in queue]
print(json.dumps(out))
'''


class LeaseGuardTests(HookCase):
    """A kill, pkill or killall that reaches another holder's slotfather lease is refused."""

    cases = fixture("lease-guard.json")

    def setUp(self):
        super().setUp()
        tag = f"lg{os.getpid() % 100000}"
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        self.worktree = self.tmp / "worktree"
        (self.worktree / ".git").mkdir(parents=True)
        (self.worktree / "desktop").mkdir()
        elsewhere = self.tmp / "elsewhere"
        (elsewhere / ".git").mkdir(parents=True)
        lanes = self.tmp / "lanes"
        lanes.mkdir()
        (lanes / "650-test.json").write_text(json.dumps({"id": "650-test", "ticket": "650", "status": "active",
                                                         "worktree": str(self.worktree)}))
        (lanes / "641-desktop-shared-host.json").write_text(json.dumps(
            {"id": "641-desktop-shared-host", "status": "active", "worktree": str(elsewhere)}))
        # Each process runs /bin/sleep under a name of its own, so pkill, killall and pgrep find only it.
        self.pids, self.markers = {}, {}
        for index, process in enumerate(self.cases["processes"]):
            marker = f"{tag}-{index:02d}-x"
            (bin_dir / marker).symlink_to("/bin/sleep")
            child = subprocess.Popen([str(bin_dir / marker), "300"], start_new_session=True)
            self.addCleanup(lambda child=child: (child.kill(), child.wait()))
            self.pids[process], self.markers[process] = child.pid, marker
        # The stand-in for the session's Claude Code process (CLAUDE_PID), with the processes started under it.
        names = [f"{tag}-s{index:02d}-x" for index, _ in enumerate(self.cases["session_children"])]
        for marker in names:
            (bin_dir / marker).symlink_to("/bin/sleep")
        session = subprocess.Popen(["/bin/sh", "-c", 'for m in "$@"; do "$m" 300 & echo $!; done; wait', "sh",
                                    *[str(bin_dir / marker) for marker in names]],
                                   stdout=subprocess.PIPE, text=True, start_new_session=True)
        self.addCleanup(lambda: (os.killpg(session.pid, 9), session.wait(), session.stdout.close()))
        for process, marker in zip(self.cases["session_children"], names):
            self.pids[process], self.markers[process] = int(session.stdout.readline()), marker
        self.pidfiles = {}
        for process, pid in self.pids.items():
            path = self.tmp / f"{process}.pid"
            path.write_text(f"{pid}\n")
            self.pidfiles[process] = path
        places = {"worktree": str(self.worktree), "elsewhere": str(elsewhere)}
        queue, self.caller_lease = [], None
        for number, (key, lease) in enumerate(self.cases["leases"].items()):
            entry = {"id": f"{number:010d}-{self.pids[lease['holder']]}", "label": lease["label"], "state": "held",
                     "count": 1, "meta": lease["meta"], "cwd": places[lease["cwd"]],
                     "lease": str(self.tmp / f"queue/{key}.json"), "pid": self.pids[lease["holder"]],
                     "pgid": self.pids[lease["holder"]], "tree": [self.pids[p] for p in lease["tree"]],
                     "env": [self.pids[p] for p in lease.get("env", [])]}
            if lease.get("start"):
                entry["start_override"] = lease["start"]
            if lease.get("caller_lease"):
                self.caller_lease = entry["lease"]
            queue.append(entry)
        (self.tmp / "queue.json").write_text(json.dumps(queue))
        (bin_dir / "slotfather").write_text(FAKE_STATUS)
        (bin_dir / "slotfather").chmod(0o755)
        self.queue = queue
        self.env.update(PATH=f"{bin_dir}:/usr/bin:/bin:/usr/sbin:/sbin", FAKE_QUEUE=str(self.tmp / "queue.json"),
                        MASTACK_LANE_RECORDS=str(lanes), SLOTFATHER_LEASE=self.caller_lease, HOME=str(self.tmp),
                        CLAUDE_PID=str(session.pid))

    def command(self, template):
        text = template
        for process, pid in self.pids.items():
            text = (text.replace(f"{{group:{process}}}", str(pid)).replace(f"{{{process}:marker}}", self.markers[process])
                    .replace(f"{{pidfile:{process}}}", str(self.pidfiles[process])))
        for process in sorted(self.pids, key=len, reverse=True):
            text = text.replace(f"{{{process}}}", str(self.pids[process]))
        self.assertNotIn("{", text, "every placeholder is filled")
        return text

    def decide(self, template, cwd=None, agent=None, script="lease_guard.py", permission_mode="default",
               entrypoint="t3-code"):
        """The hook's answer for the session's main thread, or with `agent` for a subagent of it."""
        saved = self.env.get("CLAUDE_CODE_ENTRYPOINT")
        if entrypoint is None:
            self.env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        else:
            self.env["CLAUDE_CODE_ENTRYPOINT"] = entrypoint
        try:
            payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                       "cwd": cwd or str(self.worktree / "desktop"),
                       "session_id": "session-mine", **({"agent_id": agent} if agent else {}),
                       "tool_input": {"command": self.command(template)}}
            if permission_mode is not None:
                payload["permission_mode"] = permission_mode
            return self.run_hook(script, payload)
        finally:
            if saved is None:
                self.env.pop("CLAUDE_CODE_ENTRYPOINT", None)
            else:
                self.env["CLAUDE_CODE_ENTRYPOINT"] = saved

    def assertRefused(self, output, case, decision="deny"):
        self.assertIsNotNone(output, "allowed")
        answer = output["hookSpecificOutput"]
        self.assertEqual(answer["permissionDecision"], decision)
        reason = answer["permissionDecisionReason"]
        if decision == "deny":
            self.assertIn("never to kill another holder's lease", reason)
            self.assertIn("Safe:", reason)
        else:
            self.assertIn("only the owner approves it", reason)
            self.assertNotIn("Safe:", reason)
        for label in case["leases"]:
            self.assertIn(f"lease {label} ", reason)
        for label in {lease["label"] for lease in self.cases["leases"].values()} - set(case["leases"]):
            self.assertNotIn(f"lease {label} ", reason, "only the leases it reaches are named")
        if case.get("reused"):
            self.assertIn("reused", reason)
        return reason

    def test_kills_that_reach_another_holders_lease_are_denied_naming_it(self):
        for case in self.cases["deny"]:
            with self.subTest(case["name"]):
                self.assertRefused(self.decide(case["command"]), case)

    def test_own_leases_free_processes_and_looks_pass(self):
        for case in self.cases["allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"]))
        for child in self.pids.values():
            os.kill(child, 0)  # the guard itself signalled nothing

    def test_a_subagent_owns_only_its_lane_and_worktree_not_the_sessions_leases(self):
        for case in self.cases["subagent_deny"]:
            with self.subTest(case["name"]):
                self.assertRefused(self.decide(case["command"], agent="a1"), case,
                                   "ask" if case.get("asked") else "deny")
        for case in self.cases["subagent_allow"]:
            with self.subTest(case["name"]):
                self.assertIsNone(self.decide(case["command"], agent="a1"))

    def test_an_override_asks_the_owner_on_the_permission_card_and_is_logged(self):
        for case in self.cases["asked"]:
            with self.subTest(case["name"]):
                reason = self.assertRefused(self.decide(case["command"]), case, "ask")
                self.assertIn("owner asked to stop the stuck 641 gate", reason)
        log = (self.tmp / "state" / "guard.log").read_text()
        self.assertIn("lease-guard override asked", log)
        self.assertIn("stuck 641 gate", log)
        self.assertIsNone(self.decide('LEASE_GUARD_OK="mine" kill {mine}'), "an override reaching no lease passes")

    def test_an_override_is_denied_when_no_card_reaches_the_owner(self):
        case = self.cases["asked"][0]
        self.assertRefused(self.decide(case["command"], permission_mode="auto"), case, "deny")
        self.assertRefused(self.decide(case["command"], entrypoint=None), case, "deny")
        self.assertRefused(self.decide(case["command"], agent="a1"), case, "deny")

    def test_the_dispatcher_passes_the_ask_on_and_a_deny_beats_it(self):
        case = self.cases["asked"][0]
        self.assertRefused(self.decide(case["command"], script="bash_guard.py"), case, "ask")
        reason = self.denied(self.decide(case["command"] + "; git stash", script="bash_guard.py"))
        self.assertIn("[stash]", reason)
        self.assertRefused(self.decide("kill -9 {other}", script="bash_guard.py"),
                           {"leases": ["lane-641-desktop-shared-host"]})

    def test_a_broad_kill_checks_every_process_it_reaches_also_those_outside_a_tree(self):
        """Above the per-pid limit, a process that left its lease's tree and carries its SLOTFATHER_LEASE is still
        found (an earlier shortcut kept only the pids in a lease's tree)."""
        marker = f"lgbroad-{os.getpid()}"
        lease = next(entry for entry in self.queue if entry["label"] == "lane-641-desktop-shared-host")
        sleeper = [sys.executable, "-c", "import time; time.sleep(300)", marker]
        free = {k: v for k, v in self.env.items() if k != "SLOTFATHER_LEASE"}
        children = [subprocess.Popen(sleeper, start_new_session=True,
                                     env={**free, "SLOTFATHER_LEASE": lease["lease"]} if index == 0 else free)
                    for index in range(60)]
        for child in children:
            self.addCleanup(lambda child=child: (child.kill(), child.wait()))
        lease["env"].append(children[0].pid)
        (self.tmp / "queue.json").write_text(json.dumps(self.queue))
        deadline = time.monotonic() + 30
        while len(subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True).stdout.split()) < 60:
            self.assertLess(time.monotonic(), deadline, "the sleepers did not start")
            time.sleep(0.05)
        reason = self.assertRefused(self.decide(f"pkill -f {marker}"), {"leases": ["lane-641-desktop-shared-host"]})
        self.assertIn(f"pid {children[0].pid}, outside its tree", reason)

    @unittest.skipUnless(sys.platform == "darwin", "macOS killall")
    def test_killall_by_user_alone_reaches_every_process_of_the_user(self):
        user = pwd.getpwuid(os.getuid()).pw_name
        self.assertRefused(self.decide(f"killall -u {user}"), {"reused": True, "leases": [
            "lane-641-desktop-shared-host", "scripts", "kit-verify"]})

    def test_another_lanes_worktree_owns_its_lease_and_not_the_callers(self):
        elsewhere = str(self.tmp / "elsewhere")
        self.assertIsNone(self.decide("kill {other}", cwd=elsewhere, agent="a1"))
        self.assertIsNotNone(self.decide("kill {mine}", cwd=elsewhere, agent="a1"))

    def test_a_configured_slotfather_off_path_is_asked(self):
        fake = os.path.join(self.env["PATH"].split(":")[0], "slotfather")
        self.env.update(PATH="/usr/bin:/bin", MASTACK_SLOTFATHER=fake)
        self.assertRefused(self.decide("kill -9 {other}"), {"leases": ["lane-641-desktop-shared-host"]})
        self.env["MASTACK_SLOTFATHER"] = str(self.tmp / "missing-slotfather")
        self.assertIsNone(self.decide("kill -9 {other}"))

    def test_without_slotfather_or_input_everything_passes(self):
        self.env["PATH"] = "/usr/bin:/bin"
        self.assertIsNone(self.decide("kill -9 {other}"))
        self.assertFailsOpen("lease_guard.py")
        self.assertIsNone(self.run_hook("lease_guard.py", {"tool_name": "Bash", "tool_input": {"command": "kill \"x"}}))


INSTALLED_SLOTFATHER = shutil.which("slotfather")


@unittest.skipUnless(INSTALLED_SLOTFATHER, "slotfather is not installed on this machine")
class InstalledLeaseGuardTests(HookCase):
    """The guard against the installed slotfather with a private queue (SLOTFATHER_DIR): its real `status --json
    --pid` answer for a lease whose metadata names a lane, and for one of the caller's own lane."""

    def setUp(self):
        super().setUp()
        self.worktree = self.tmp / "worktree"
        (self.worktree / ".git").mkdir(parents=True)
        lanes = self.tmp / "lanes"
        lanes.mkdir()
        (lanes / "650-test.json").write_text(json.dumps({"id": "650-test", "status": "active",
                                                         "worktree": str(self.worktree)}))
        (self.tmp / "memory").write_text("8000 1\n")
        self.env.update(SLOTFATHER_DIR=str(self.tmp / "queue"), SLOTFATHER_LEGACY_DIRS="", SLOTFATHER_CORES="12",
                        SLOTFATHER_LOADAVG="0", SLOTFATHER_MEMORY_FILE=str(self.tmp / "memory"),
                        SLOTFATHER_POLL="0.05", MASTACK_LANE_RECORDS=str(lanes))
        for key in [k for k in self.env if k in ("SLOTFATHER_LEASE", "SLOTFATHER_COUNT", "SLOTFATHER_YIELD")]:
            del self.env[key]

    def lease(self, lane):
        """A `slotfather run` whose child is a shell that records its own pid, then sleeps."""
        out = self.tmp / f"{lane}.pid"
        holder = subprocess.Popen([INSTALLED_SLOTFATHER, "run", "-n", "1", "--label", f"lane-{lane}", "--meta",
                                   f"lane={lane}", "--", "/bin/sh", "-c", f'echo $$ > "{out}"; exec sleep 300'],
                                  env=self.env, start_new_session=True, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (os.killpg(holder.pid, 9), holder.wait()))
        deadline = time.monotonic() + 30
        while not (out.exists() and out.read_text().strip()):
            self.assertLess(time.monotonic(), deadline, "the lease's command did not start")
            time.sleep(0.05)
        return int(out.read_text())

    def decide(self, command):
        return self.run_hook("lease_guard.py", {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                                "cwd": str(self.worktree), "session_id": "s", "agent_id": "a1",
                                                "tool_input": {"command": command}})

    def test_the_real_queue_answer_denies_another_lane_and_passes_the_callers(self):
        other, mine = self.lease("641-other"), self.lease("650-test")
        output = self.decide(f"kill -9 {other}")
        self.assertIsNotNone(output, "allowed")
        self.assertIn("lease lane-641-other ", output["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIn("lane 641-other", output["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(self.decide(f"kill -9 {mine}"))


if __name__ == "__main__":
    unittest.main()
