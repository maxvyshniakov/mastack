# Changelog

## Unreleased

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
