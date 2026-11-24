# Changelog

## Unreleased

- `release_guard`: a standing permission for routine releases. A project that
  declares `release_standing` (packages, optionally levels) in
  `docs/agents/hooks.json` on `origin/main` gets releases, publishes, `v*` tag
  pushes, release workflow dispatches and `promote --ship` through without a
  go-ahead when local facts show a patch or minor of an already-tagged package
  with no Breaking CHANGELOG entry and no access change. Majors, breaking
  changes, first publications and access changes stay the owner's; the guard
  now also refuses `gh repo edit --visibility`, `gh repo create --public`,
  `npm access` changes and Pages writes through `gh api`, and release or
  publish `gh workflow run`. What it refuses it asks on a permission card only
  where the card reaches a person (T3 Code Claude sessions in default,
  accept-edits or full-access mode); elsewhere, Codex included, it denies and
  names the missing fact. `MASTACK_RELEASE_OK` keeps working. `release` and
  `orchestrate` follow the standing permission.
- `orchestrate` Finish: every `Least sure`, `Nearby`, `Friction` and `Upstream`
  line and every review lead is routed before the batch report, and the report
  names the last `usage-audit` and `test-audit` and runs the one that is due.
- `orchestrate` pushes a green, review-resolved batch to the everyday branch
  itself, in small batches, unless the project's publishing doc says the
  branch waits for the owner; the release branch, releases and publications
  stay the owner's command.
- `cross-review` Depth: an owner-decided look with a guard, tooling outside
  the shipped package and a few-line CI or config change need no review; the
  depth is chosen when the lane starts, and one exempt lane in five is
  reviewed after the fact.
- `retro`: a review finding that recurred across tasks in the session moves
  from a reviewer rule to a mechanical check; a check that runs on one OS only
  gets its OS-specific code tested against fake inputs locally; the report
  drops "what went well", and every finding names the artifact to change.
- `orchestrate` reviews a lane before it lands: the lane check and the review
  run together on the committed tree, findings go to the same implementer in
  the same lane, and the lane lands once (was: review after the land, then a
  fix lane). The brief says whose the lane check is (`Check: mine | yours`).
  The fix-lane path remains for lanes that landed unreviewed. `cross-review`
  gains a Unit step: one contract per review, large diffs split by subsystem,
  small lanes of one subsystem reviewed together, docs-against-code as its
  own pass, a second reviewer from another family.
- `cross-review` reviewers now answer a fixed brief
  (`references/reviewer-brief.md`): per finding a confidence, a falsifier, the
  guard that should have caught it and a fix direction; up to five leads wider
  than the diff (class, symmetry, wrong level, unasked); and a triage table.
  A fix starts from the falsifier as a failing test. New "Owner's decisions"
  step: before a question reaches the owner, the session histories, tracker
  and blame are searched for the answer they already gave; `orchestrate`
  step 9 routes questions through it. The implementer report gains a `Nearby`
  line with the same kind of leads, and `Least sure`, `Decisions`, `Friction`
  and `Upstream` lines.
- Worktrees now default to `<repo>/.claude/worktrees/<name>` in `orchestrate`
  (unless `docs/agents/publishing.md` names another place), `cleanup` also
  inventories `<repo>/.claude/worktrees/` and temp-dir worktrees listed by git,
  and `git_guard` (`bash_guard`) refuses `git worktree add` targets outside
  `<repo>/.claude/worktrees/` and the session scratchpad (`/tmp`, `$TMPDIR`),
  pointing at `junkfather own --kind worktree` (mastack#13).
- New Bash check `release_guard` (`hooks/release_guard.py`) and `release` skill:
  `bash_guard` refuses `npm`/`bun`/`pnpm`/`yarn npm publish`,
  `bun run release:publish`, `repo-kit release`, `gh release create`, pushing a
  `v*` tag, and `lanefather promote --ship` (also in chains and `sh -c`) unless
  the environment carries an explicit owner go-ahead in `MASTACK_RELEASE_OK`
  (not set in the command itself).
- `hooks/register.py` reads `HOOK_TIMEOUT` and `EVENTS` directly from
  `bash_guard`, `lifecycle`, `agent_role` and `friction_hook`, and shares
  `hook_io.config_dir()` across the hooks and installer.
- Extract `hooks/shell.py` (`read`, `Word`, `unwrap`, `program`, `show`,
  `strip_heredocs`) out of `hooks/unguarded_sequence.py` so the checks that
  parse depend on a shared shell reader instead of on another check.
- New skill `usage-audit` and `[pricing.*]` price weights in `models.toml`:
  defines per-model weights (`input`, `output`, `cache_read`,
  `cache_write_short`, `cache_write_long`, `cache_write_default`,
  `tier_multiplier`) across Anthropic, OpenAI/Codex, and Google/Antigravity
  models for `tokenfather`, and adds `skills/usage-audit/SKILL.md` to run
  `tokenfather report` and `lanefather stats`, answer the multi-provider
  usage-audit questions, and route findings to harness settings, orchestrate
  skill/model policy, project checks, or tools/hooks (mastack#20).
- `models.toml`, `bin/role`, `hooks/model_roles.py`, `orchestrate`: add the
  `google` / `antigravity` family (`neon` / `gemini-4-neon`, `argon` /
  `gemini-4-argon`, `flash` / `gemini-3.8-flash`), provider-specific reasoning
  options (`effort`, `model_reasoning_effort`, `thought_level`), and
  `[providers.<family>]` cache/context-budget metadata. Allow cross-family
  review (`not_family = true`) and `visual`/`implement`/`scout` roles to route
  across all three families (`bin/role` adds `--family` and `--exclude-family`,
  preserving existing Claude/Codex defaults). Document T3 Code `delegate_task`
  (`target.model` + `target.options.thought_level`) alongside Claude `Agent`
  and `codex exec` in `orchestrate` (mastack#25).
- `orchestrate` (`implementer.md`) and `hooks/friction_hook.py`: add
  range-reading and output-capping rules for tool calls, and journal Bash
  results over 8,000 characters to the friction journal (`kind="note"`,
  `rule="large-bash-output"`) naming the command (mastack#23).
- New PreToolUse Agent hook (`hooks/agent_role.py`, registered by
  `bin/install`): reads the launch's role from the prompt (`Role: <role>` or
  `[role: <role>]`) or description and fills missing `model` and `effort` from
  `models.toml`; launches without a known role pass through unchanged.
  `orchestrate` step 4 names the role in the brief and passes the role's model
  and effort on every launch, including fix rounds and scouting (mastack#24).
- `orchestrate`: replace the fixed chain-per-agent and review-fix resume rules
  with warm-vs-fresh criteria (reuse when idle under ~50 minutes, context under
  ~150–200K, and same code; otherwise start a fresh agent with a brief or WIP
  commit) (mastack#21).
- `orchestrate`: the implementer brief names the lane's focused checks for the
  edit-check loop; `lanefather check` runs once on the committed tree before
  hand-back, and a red lane check is fixed with focused checks before `--rerun`
  (mastack#22).
- `orchestrate`, `cross-review`: triage finished reviews on arrival (or when
  the lane list/stop hook reports them) while the diff is fresh, enforced by
  the Lanefather gate before further lands (mastack#11).
- `browser-verify`: distinguish the canonical background Safari transport from
  WebDriver focus handback, use headless engines for ordinary static layout, and
  require native acceptance for replacement launchers (mastack#19).

## 0.4.1

- GitHub enforces promotion from a checked dev commit for updates to main.

## 0.4.0

- Develop on `dev`. Each `bin/promote X.Y.Z` publishes a tagged release on `main`.

- `orchestrate`: the coordinator registers a lane before launching it, and
  the implementer brief is a template with the lane's commands filled in:
  worktree, check, the hand-back, and what the coordinator does after (land,
  review, the one fix round). The implementer opens a command's `--help` only
  after it fails, runs long checks in the background and waits for their
  completion notice, hands back after a green check and stops, and polls no
  lane state; `lanefather wait <id> --for <state>` (fathers#175) is for the
  rare wait it needs. The coordinator waits for the agent's completion
  notice, not on `lanefather list` (mastack#16).
- `orchestrate`, `cross-review`: a fix round starts only through the lane
  tool's fix-round path (`lanefather review <id> --fix-lane`, or `start
  <fix-id> --fix-of A,B,C` for several lanes, fathers#174), never a plain
  `start`, which Lanefather reviews at land; a review of fix work that runs
  anyway opens no new round, and its findings are marked `rejected: fix round, not reviewed again (one review per lane)`
  so the lane finishes (mastack#17).
- `models.toml`: a `scout` role for read-only scouting in the repository,
  Sol at medium effort while at least 15% of the weekly Codex limit is left,
  then Sonnet at medium. `orchestrate` runs `scripts/role scout` before such
  a task: Sol headless through `[cli.codex].run` in a read-only sandbox with
  stdin closed, Sonnet through the Agent tool. Judgment and proposals stay
  with `design` (mastack#18).
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
- The friction journal writer (`hooks/friction_journal.py`) takes the format
  from `hooks/friction-contract.json`, a pinned copy of repo-kit's
  `friction-contract.json` with its SHA-256 in `FRICTION_CONTRACT_SHA256`;
  change it only by copying repo-kit's file and updating the hash. Version,
  fields, kinds, limits, session variables and the fingerprint rule come from
  it, and `tests/friction_contract_test.py` runs every build, validate and
  fingerprint case of the copy against the writer, and compares the copy with
  a repo-kit checkout (`$REPO_KIT_DIR`, else `~/repo-kit`) when one has the
  file, naming the parts that drifted. Following the contract, lines are now
  compact JSON in schema order as repo-kit writes them, the detail limit
  counts UTF-16 units and `append` cuts a long detail as `event` does, and an
  event with a mistyped optional field, `v: true` or a time JavaScript's
  `Date.parse` rejects is no longer written; every time it takes (24:00, day
  31 of any month, lowercase `z`, `+0200`) still is. A refused event is
  logged to the hooks' `guard.log` instead of vanishing. Still stdlib-only
  Python; no node at hook time.

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
