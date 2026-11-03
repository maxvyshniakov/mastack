# Checks

## Focused
- A changed skill: reread it against the no-op test (would a strong model do
  this without the line?) and run its scenarios: `bin/eval <skill>`.
- A changed scenario or `evals/lib.sh`: `bin/eval <skill> --agent none` must
  fail its grade, then a real run must pass.
- `tests/install_test.sh` after changing the installer.

## Full gate
- `bin/check`: the private-detail scan, then every tracked `*_test.sh` and
  `*_test.py`. The pre-push hook runs it.

## Heavy checks
- `bin/eval` starts real agent sessions and costs tokens, not CPU; run it on
  purpose, not on every push.

## Pins
- None.
