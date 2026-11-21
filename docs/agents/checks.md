# Checks

## Focused
- A changed skill: reread it against the no-op test (would a strong model do
  this without the line?). Run its scenarios, `bin/eval <skill>`, only when the
  change alters what the agent does: when the skill starts, a step, what it
  reports, what it must never do. A mechanical edit (a path, a command's name,
  a link, wording that means the same) needs no run; say in the report that it
  was skipped as mechanical.
- A changed scenario or `evals/lib.sh`: `bin/eval <skill> --agent none` must
  fail its grade, then a real run must pass.
- `tests/install_test.sh` after changing the installer.
- `python3 tests/test_<check>.py` (and `tests/test_bash_guard.py`) after
  changing a hook or its fixtures; a new check gets deny and allow fixtures in
  `hooks/fixtures/` and a row in `bash_guard.CHECKS`.

## Full gate
- `bin/check`: the private-detail scan, then every tracked `*_test.sh`,
  `*_test.py` and `test_*.py`. The pre-push hook runs it.

## Heavy checks
- `bin/eval` starts real agent sessions and costs tokens, not CPU; run it on
  purpose, not on every push.

## Pins
- None.
