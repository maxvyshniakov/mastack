#!/usr/bin/env python3
"""The friction journal writer against repo-kit's format contract: the pinned copy, its hash and every golden case.

hooks/friction-contract.json is a pinned copy of repo-kit's friction-contract.json. A repo-kit checkout
($REPO_KIT_DIR, else ~/repo-kit) is compared with it when one is found; without one that test is skipped.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
COPY = ROOT / "hooks" / "friction-contract.json"
sys.path.insert(0, str(ROOT / "hooks"))

import friction_journal as fj  # noqa: E402

CONTRACT = json.loads(COPY.read_text(encoding="utf-8"))
# The case groups a writer runs, and the ones only an exporter (repo-kit's `friction export`) runs.
WRITER_CASES = {"build", "write", "validate", "fingerprint"}
EXPORTER_CASES = {"redact"}


def differing_parts(ours: dict, theirs: dict) -> list[str]:
    """The parts two contracts disagree on, one level deep: `schema.kinds`, `cases.build`, ..."""
    found = []
    for part in sorted(set(ours) | set(theirs)):
        mine, other = ours.get(part), theirs.get(part)
        if mine == other:
            continue
        if isinstance(mine, dict) and isinstance(other, dict):
            found += [f"{part}.{key}" for key in sorted(set(mine) | set(other)) if mine.get(key) != other.get(key)]
        else:
            found.append(part)
    return found or ["formatting only"]


def built(case: dict) -> dict:
    now = datetime.fromisoformat(case["now"])
    return fj.build_event(case["fields"], cwd=case["cwd"], env=case["env"], now=now)


class PinnedCopy(unittest.TestCase):
    def test_the_copy_matches_its_recorded_hash(self):
        self.assertEqual(hashlib.sha256(COPY.read_bytes()).hexdigest(), fj.FRICTION_CONTRACT_SHA256,
                         "hooks/friction-contract.json changed: copy repo-kit's friction-contract.json as is and "
                         "update FRICTION_CONTRACT_SHA256 in hooks/friction_journal.py")

    def test_the_writer_takes_its_constants_from_the_copy(self):
        schema = CONTRACT["schema"]
        self.assertEqual(fj.SCHEMA, schema["version"])
        self.assertEqual(list(fj.KINDS), schema["kinds"])
        self.assertEqual(list(fj.FIELDS), [field["name"] for field in schema["fields"]])
        self.assertEqual((fj.DETAIL_LIMIT, fj.LINE_LIMIT), (schema["limits"]["detail"], schema["limits"]["line"]))
        self.assertEqual(list(fj.SESSION_ENV), CONTRACT["build"]["session"]["env"])

    def test_every_case_group_is_run_or_named_exporter_only(self):
        self.assertEqual(set(CONTRACT["cases"]), WRITER_CASES | EXPORTER_CASES,
                         "the contract has a new case group: run it here, or name it exporter-only")

    def test_drift_is_named_by_part(self):
        theirs = json.loads(json.dumps(CONTRACT))
        theirs["schema"]["kinds"].append("new-kind")
        theirs["cases"]["build"].pop()
        theirs["extra"] = 1
        self.assertEqual(differing_parts(CONTRACT, theirs), ["cases.build", "extra", "schema.kinds"])
        self.assertEqual(differing_parts(CONTRACT, CONTRACT), ["formatting only"])

    def test_the_copy_is_repo_kits_file(self):
        directory = pathlib.Path(os.environ.get("REPO_KIT_DIR") or pathlib.Path.home() / "repo-kit").expanduser()
        upstream = directory / "friction-contract.json"
        if not upstream.is_file():
            self.skipTest(f"no repo-kit contract at {upstream}; set REPO_KIT_DIR to compare the pinned copy")
        if upstream.read_bytes() == COPY.read_bytes():
            return
        drift = differing_parts(CONTRACT, json.loads(upstream.read_text(encoding="utf-8")))
        self.fail(f"hooks/friction-contract.json differs from {upstream} in {', '.join(drift)} "
                  f"(theirs {hashlib.sha256(upstream.read_bytes()).hexdigest()}): copy it and update "
                  "FRICTION_CONTRACT_SHA256 in hooks/friction_journal.py")


class GoldenCases(unittest.TestCase):
    def test_build_cases_give_the_exact_line(self):
        for case in CONTRACT["cases"]["build"]:
            with self.subTest(case["name"]):
                event = built(case)
                self.assertEqual(list(event), list(fj.FIELDS))
                self.assertEqual(fj.line(event), case["line"])
                self.assertEqual(fj.problems(json.loads(case["line"])), [])

    def test_write_cases_give_the_line_or_a_logged_refusal(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="mastack-friction-write-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        state = tmp / "state"
        patcher = mock.patch.dict(os.environ, {"MASTACK_HOOK_STATE": str(state)})
        patcher.start()
        self.addCleanup(patcher.stop)
        for index, case in enumerate(CONTRACT["cases"]["write"]):
            with self.subTest(case["name"]):
                journal = tmp / f"{index}.jsonl"
                written = fj.append([case["event"]], {"FRICTION_JOURNAL": str(journal)})
                if "problems" in case:
                    self.assertEqual(fj.problems(fj.journal_event(case["event"])), case["problems"])
                    self.assertEqual((written, journal.exists()), (0, False))
                    log = (state / "guard.log").read_text(encoding="utf-8")
                    self.assertIn(f"friction journal refused a {case['event'].get('kind')} event", log)
                    self.assertIn(case["problems"][0], log, "the refusal names its problems")
                else:
                    self.assertEqual(fj.line(case["event"]), case["line"])
                    self.assertEqual((written, journal.read_text(encoding="utf-8")), (1, case["line"] + "\n"))

    def test_validate_cases_give_the_problems_in_order(self):
        for case in CONTRACT["cases"]["validate"]:
            with self.subTest(case["name"]):
                self.assertEqual(fj.problems(json.loads(case["line"])), case["problems"])

    def test_fingerprint_cases(self):
        for case in CONTRACT["cases"]["fingerprint"]:
            with self.subTest(case["name"]):
                self.assertEqual(fj.fingerprint(*case["parts"]), case["fingerprint"])

    def test_append_writes_the_golden_lines(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="mastack-friction-contract-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        journal = tmp / "events.jsonl"
        cases = CONTRACT["cases"]["build"]
        self.assertEqual(fj.append([built(case) for case in cases], {"FRICTION_JOURNAL": str(journal)}), len(cases))
        self.assertEqual(journal.read_bytes(), "".join(case["line"] + "\n" for case in cases).encode("utf-8"))

    def test_event_builds_the_same_event_as_the_contract_rule(self):
        case = next(c for c in CONTRACT["cases"]["build"] if c["fields"].get("ts"))
        fields = case["fields"]
        made = fj.event(package=fields["package"], kind=fields["kind"], project=fields["project"], source=fields["source"],
                        ts=fields["ts"], component=fields["component"], rule=fields["rule"], detail=fields["detail"],
                        session=fields["session"], why=fields["why"], file=fields["file"], fp=fields["fingerprint"])
        self.assertEqual(fj.line(made), case["line"])


if __name__ == "__main__":
    unittest.main()
