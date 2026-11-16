# Changelog

## Unreleased

- Lifecycle `PreToolUse` entries can rewrite a Bash call: `"rewrite": true`
  makes the entry's answer (`hookSpecificOutput.updatedInput`) the call's new
  input, passed on by `bash_guard` without a permission decision of its own,
  never for a denied call; `"background": true` runs an entry only for
  `run_in_background` calls; `"allow": [rules]` has `bin/install` add those
  permission rules to Claude Code's settings, recorded and removed again once
  no entry lists them; `"replaces": [commands]` removes Bash handlers a tool
  registered itself before. Junkfather uses it to own agents' background
  commands. Every lifecycle command now runs in a process group of its own,
  killed whole on its timeout, so `sleep 600 & wait` leaves nothing behind.
- New Bash check `docker_desktop`: `bash_guard` refuses quitting, killing or
  restarting Docker Desktop (`osascript` quit, `killall`, `pkill`, `kill` of a
  pid found by name, `docker desktop stop`/`restart`) and opening it in front;
  the refusal names `docker compose restart`, `docker compose up -d
  --force-recreate`, `docker info` and the hidden start `open -gja Docker`.
- New Bash check `simctl_boot`: `bash_guard` refuses `xcrun simctl boot` (and
  `bootstatus -b`) outside `junkfather own --kind simulator`, which shuts the
  simulator down at session end or its TTL, and shows the wrapped command.
  Without junkfather installed every command passes.
- `orchestrate`: writes to the project's own tracker (evidence comments,
  follow-up tickets, fixes to its own comments) need no owner confirmation;
  push, release, publish and early closing still follow `publishing.md`. A lane
  is finished in the lane tool as soon as its last review finding is marked,
  not at batch end, since finished lanes otherwise fill the disk until new
  lanes are refused. The implementer brief now stops loops waiting on a stopped
  command, waits on completion notices instead of polling, and checks that no
  process of its own is left before reporting.

- New `bin/role <role> [--implementer-family F] [--json]`: evaluates
  `models.toml` with the live quotas its conditions name (the weekly Codex
  limit through `codex app-server`) and prints the winning model, effort,
  headless command and note, with the reason each earlier choice was skipped.
  An unreadable quota counts as not met. `cross-review`, `orchestrate`,
  `research` and `rate` run it through a `scripts/role` link in the skill
  instead of reading the table.
- New Bash check `codex_credits`: `bash_guard` refuses a headless `codex exec`
  or `codex review` while the weekly Codex limit is under the review role's
  threshold, since such runs are billed to credits. The refusal names what
  `role review` picks instead and the owner's override
  (`MASTACK_ALLOW_CREDITS=1` before the command). It sees through `env`,
  `timeout`, `xargs`, `npx`, `eval`, `slotfather run` and `junkfather own`.
  The quota read is reused for five minutes or until the window resets; a
  missing or silent `codex` lets every command pass.
- `models.toml`: the implement role is Opus at effort medium.

- `bin/check` before a push also scans the messages of commits not yet on
  origin/main, as the CI history scan does, so a finding in a commit message no
  longer surfaces only after the push. A message line that only closes or names
  this repository's own issue (`Closes #N`) is allowed in both.

- New Bash check `slot_label`: `bash_guard` refuses a `slotfather run` without
  `--label`, or labelled with the directory's name or only generic words, since
  everyone reads labels on the dashboard to decide whether to wait or
  reprioritize. The refusal gives the format `<task or ticket> <what it does>`
  and an example built from the command. Wrappers that lease on their own
  (Lanefather, repo-kit, project verify scripts) are not affected.

- New skill `test-audit`: a periodic, read-only audit of a test suite (monthly,
  or when gate time or flaky failures rise). It ranks suites by run history
  and reports fakes nobody checks against the real thing, tests at the wrong
  layer, sleeps and timing asserts, per-test setup cost, tests that outlived
  their purpose, with counts, `file:line` and a ratchet to propose. `retro`
  runs it when a test caused the trouble.
- `tdd` has a "Cost of a test" section: the cheapest layer that observes the
  behavior, no fixed sleeps, timing asserts only in the perf suite, snapshots
  only when read, fakes checked against the real implementation. Its report
  and the `orchestrate` implementer report list each new test with its layer
  and run time, and `cross-review` gives the reviewer a test baseline.
- Friction journal: moments agents misread or misuse your packages, one line
  each in `$XDG_STATE_HOME/friction/events.jsonl` (repo-kit's friction schema),
  configured in `~/.config/mastack/friction.json`. A `PostToolUse` Bash hook
  (`hooks/friction_hook.py`, registered by `bin/install` when the file exists)
  logs TypeScript errors about the configured packages; `bin/friction scan`
  reads new Claude Code and Codex sessions for type errors, owner corrections
  and misuse, each with its reason; `bin/friction vendor` logs vendored copies'
  local patches against their upstream version; `bin/friction plist` prints a
  daily launchd agent. New user-invoked skill `friction` (`/friction <text>`)
  logs a correction. `friction-audit` reads the journal first, then transcripts.

- New skill `babysit-pr`: takes an open pull request through its failing checks
  and review threads. Each finding is verified first; a real bug gets a failing
  test that is also run against the base branch; every worked thread gets a
  reply; labels and CI triggers that maintainers own are reported, not set.

- Lifecycle hooks: `lifecycle` in `~/.config/mastack/hooks.json` lists commands
  per Claude Code event (`SubagentStop`, `SessionEnd`, `Stop`, `SubagentStart`,
  `SessionStart`), which `bin/install` registers through one dispatcher,
  `hooks/lifecycle.py`, and Bash-call observers (`PreToolUse` with `contains`)
  that `bash_guard.py` runs after its checks. They get the event's JSON, never
  block and fail open.

- `orchestrate` gives tickets a lifecycle: every lane carries its ticket, the
  landing merge says `Fixes #N`, a green land labels the ticket `integrated`
  and comments the merge, branch, push state, checks and preview, and a release
  or promote to the default branch comments its version or SHA on each ticket
  it closed. Follow-ups stay on the ticket as checklist items or linked issues.

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
