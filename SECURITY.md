# Security

## Reporting

Report a vulnerability privately through GitHub's
[private vulnerability reporting](https://github.com/maxvyshniakov/mastack/security/advisories/new)
for this repository, not in a public issue. Include the file, the command or
input that triggers it, and what it lets an agent or another user do. This is a
personal project: expect an answer within days, not hours. Fixes land on `main`
and are noted in [CHANGELOG.md](CHANGELOG.md).

## What runs on your machine

Read these before installing; they are short.

- **Skills** are Markdown instructions. They run nothing by themselves; your
  agent decides what to execute, under its own permission settings. Two ship
  scripts: `video-feedback/scripts/transcribe_video_feedback.py` (runs `ffmpeg`
  and a local Whisper on a file you name) and its test.
- **`bin/install`** creates symlinks in `~/.claude/skills` and
  `~/.agents/skills` (or `--target`), reads `.claude/skills` and
  `.agents/skills` of every Git repository directly under `~`
  (`$MASTACK_SCAN_ROOT`) to find name clashes, and, unless `--skip hooks`,
  adds one `PreToolUse` entry to `~/.claude/settings.json` after writing a
  backup. `--dry-run` shows all of it first.
- **The Bash hook** (`hooks/bash_guard.py`) receives every Bash command your
  Claude Code agent is about to run. It parses the text and never executes it.
  To decide, it may run `git rev-parse` in a directory the command names,
  `slotfather status`, `ps`, and `pgrep` or `lsof -t` with the arguments the
  command itself gives them, and read a pid file the command names with
  `cat`. It makes no network requests and writes only `guard.log` in its
  state directory. It fails open: on any error the command runs.
- **`bin/eval`** starts real Claude Code or Codex sessions in scratch
  directories under the system temp directory, with narrow permissions (see
  [evals/README.md](evals/README.md)). It spends tokens.

The hooks are guardrails against an agent's mistakes, not a security boundary:
a determined agent can avoid them, for example by writing the command into a
script first. Keep your agent's own permission settings as the boundary.

## Scope

In scope: anything in this repository that runs code, writes files or changes
settings in a way its documentation does not say, or that a crafted command,
repository or configuration file can turn against the user. Out of scope: an
agent ignoring a skill's instructions, and the third-party tools listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
