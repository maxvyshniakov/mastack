# Contributing

mastack is one developer's working setup, so the bar for a change is that it
fixes something that went wrong, or removes a line a strong model no longer
needs. Issues describing an incident (what the agent did, what it should have
done, the skill involved) are the most useful contribution. Pull requests are
welcome; open an issue first for anything larger than a fix.

A change needs:

- **Skills**: the no-op test. Every line must change what a strong model does;
  a line it would follow anyway goes. The description says when to use the
  skill, in English, and stays short. A behaviour that once went wrong gets a
  scenario under `evals/` (see [evals/README.md](evals/README.md)); check that
  `bin/eval <skill> --agent none` fails its grade.
- **Hooks**: deny and allow fixtures in `hooks/fixtures/` and, for a new check,
  a row in `bash_guard.CHECKS`. Checks fail open and never run the command.
- **Installer**: a case in `tests/install_test.sh`.
- **Everything**: `bin/check` passes. It scans for private details (home paths,
  addresses, e-mails, tokens, issue references) and runs the tests; enable the
  pre-push hook with `git config core.hooksPath .githooks`. User-visible
  changes get a line under `Unreleased` in [CHANGELOG.md](CHANGELOG.md).

Project facts for agents working on this repository are in
[docs/agents/](docs/agents/). Contributions are accepted under the
repository's [MIT license](LICENSE).
