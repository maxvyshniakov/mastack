# Changelog

## Unreleased

- Ready for a public repository: README for outside readers (requirements,
  adopting part of the pack, the project contract and the model table),
  SECURITY.md, CONTRIBUTING.md, and THIRD_PARTY_NOTICES.md with the MIT
  notice for the ideas taken from Matt Pocock's skills (moved out of LICENSE,
  which now holds the project's MIT license alone). CI runs `bin/check` and
  `bin/check --history` on pull requests with a read-only token.
- The lease guard finds slotfather at `$MASTACK_SLOTFATHER` or `slotfather` in
  `hooks.json` before `PATH` and `~/.local/bin`.

- The sequence guard recognizes Lanefather commands and known global `--config`
  options, plus project wrappers declared by `lanefather_commands`. Absolute/env/
  interpreter forms share the same narrow mutation checks; display/help and
  verification neighbours keep passing. Wrapper failures still gate later mutations.

- Bash hooks for Claude Code: `hooks/bash_guard.py` runs git-guard,
  unguarded-sequence, zsh word-split, a new pgrep self-match check, the
  slotfather lease guard and the macOS shell pitfalls in one process (about
  30 ms per Bash call instead of five processes). `bin/install` registers it in
  `~/.claude/settings.json` (name `hooks` in `--only`/`--skip`, `--settings
  FILE`), replaces the per-check entries it supersedes and backs the file up;
  `--dry-run` prints the diff. Machine settings live in
  `~/.config/mastack/hooks.json` (`hooks/hooks.example.json`), which install
  requires; a project names its own mutating steps in `docs/agents/hooks.json`
  (CONTRACT.md).

- New `browser-verify` skill: real Chromium, Firefox, WebKit and Safari
  (Technology Preview) without taking the owner's screen, the waits a
  screenshot needs, and what no driver can check. `checks.md` names each
  engine's launcher in "Browser and visual".

## 0.3.1

- `bin/install` skips repositories listed in `~/.config/mastack/ignore`, and
  their worktrees, when it looks for shadowed skills.

## 0.3.0

- CONTRACT.md: new `docs/agents/orchestration.md` (lane tool, report labels,
  review policy, owner queue, implementer brief additions), read by
  `orchestrate`.
- New contract fields: release-branch words and worktree placement in
  `publishing.md`; "Install, deploy, restart" (replaces "After publish") for
  steps with or without a publish; a Review section in `checks.md` with project
  review rules and a reviewer-model override; research notes in `domain.md`.
- `push`, `finish`, `cleanup`, `cross-review`, `research` and `orchestrate`
  read those fields; a missing section means the skill's default.

## 0.2.4

- `bin/install` checks every Git repository directly under `~` for shadowed
  skills, plus `--project` and `~/.config/mastack/projects`; worktrees are
  marked as copies of their repository.

## 0.2.3

- `bin/install --only a,b` and `--skip a,b` pick skills, also for `--uninstall`
  and `--dry-run`.
- `bin/install` reports project skills that a pack skill would shadow (from
  `--project` or `~/.config/mastack/projects`) and holds those pack skills back
  unless `--force`.
- README and CONTRACT.md state the real precedence: in Claude Code a user skill
  beats a project skill of the same name; Codex shows both, and its choice is
  undocumented.
- `bin/check` also runs the tracked tests.

## 0.2.2

- `cleanup` handles a worktree folder that git leaves behind with ignored files:
  compare with the main checkout, delete only when nothing is unique.

## 0.2.1

- Descriptions rewritten as invocation instructions: when to use the skill
  first, in English, without trigger phrases in other languages.
- `cleanup` also inventories folders next to the repository (`<repo>-*`):
  worktrees, orphans, clones and plain folders, and asks about the last two.
  Work saved before a removal goes to the state directory, not next to the
  repository.
- `orchestrate` names lane worktrees `<repo>-<lane>` next to the repository.
- Evals for push, commit and deps-update also check that the skill was loaded.

## 0.2.0

- Skills: `to-spec`, `roadmap`, `prototype`, `research`, `orchestrate` (with an
  implementer brief), `deps-update`, `rate`, `friction-audit`, `agent-docs`,
  `retro`, `reprompt` (user-invoked), `video-feedback` (with its transcription
  script and tests; artifacts default to the temp directory).
- `rate` scores each criterion as `<criterion>: <n>/10 - <gap>` and ends with
  `Total: <n>/10`.
- `bin/eval` records Claude's events in `agent.jsonl`; `tool_uses` in
  `evals/lib.sh` lists the tool calls for grade blocks. Scenarios for
  `deps-update` and `rate`.
- `bin/check` allows issue references under the placeholder owners `owner/`
  and `acme/`.
- README: install notes; `models.md` states the visual and two-lens rules as
  the author's preferences.

## 0.1.0

- Skills: `grill-me`, `critique`, `architecture`, `tdd`, `debug`,
  `cross-review`, `commit`, `push`, `release`, `finish`, `cleanup`, `status`,
  `handoff`.
- `CONTRACT.md`: the `docs/agents/*.md` files skills read from a project.
- `models.toml` and `models.md`: one table of roles, models and fallbacks.
- `bin/install` links skills into `~/.claude/skills` and `~/.agents/skills`.
- `bin/check` finds private details in the tree or the whole history.
- `bin/eval` with scenarios for `push` and `commit`.
