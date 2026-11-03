# Project contract

mastack skills hold the process; each project holds its facts. A skill reads the
files below at fixed paths. When a file is missing, the skill says so and does
not guess. Keep each file short: it states facts and commands, and links to the
longer docs it summarises instead of copying them.

| File | Read by |
|---|---|
| `docs/agents/publishing.md` | `push`, `release`, `finish`, `cleanup` |
| `docs/agents/checks.md` | `commit`, `tdd`, `debug`, `push` |
| `docs/agents/domain.md` | `grill-me`, `architecture`, `tdd`, `debug` |
| `docs/agents/issue-tracker.md` | `status`, `cross-review`, `commit` |

`AGENTS.md` stays the entry point and points at these files; it does not repeat
them.

## `docs/agents/publishing.md`

```markdown
# Publishing

## Branches
- Everyday destination: `dev`. Release destination: `main`.
- `main` only receives a SHA that `dev` receives in the same push.
- Base branch for cleanup: `dev`.

## Gate
- What runs before a push and who runs it, e.g. "the pre-push hook runs
  `<command>` on the pushed commits; do not run it by hand first".

## Push
- Command, e.g. `<promote-tool> promote <sha>` for `dev` and
  `<promote-tool> promote <sha> --ship` for `dev` and `main`; or
  `git push origin <sha>:refs/heads/dev` when there is no tool.
- Landing a task branch, e.g. "rebase onto `origin/dev`, push the tip".

## CI
- Workflows per branch, how to find the run for a SHA, how to tell an
  infrastructure failure, when the push counts as finished.

## Release
- How to cut a version and when; how to publish, from where; what waits for CI.
- Downstream steps a release triggers and who must approve them; any standing
  approval, with its scope.

## After publish
- Install or deploy steps, each with how to verify it.

## Report
- What the push report must include beyond the defaults.
```

## `docs/agents/checks.md`

```markdown
# Checks

## Focused
- Per area: the command that checks one change quickly (a test file, a filter).

## Full gate
- The command, how long it takes, what it covers, when to run it (usually once,
  before the push, or only through the hook).

## Heavy checks
- Which commands are heavy and the wrapper that takes a machine slot for them,
  e.g. `slotfather run -n 2 -- <command>`.

## Browser and visual
- How to run them, how to check a changed screen, where pictures go.

## Pins
- Every pinned dependency or tool version kept for a reason, with the reason
  and the condition for removing it.
```

## `docs/agents/domain.md`

```markdown
# Domain
- Glossary: `<path>` (one per context, or a map of contexts).
- ADRs: `<dir>`, numbered `0001-slug.md`.
- Compatibility policy, if the project has one.
```

## `docs/agents/issue-tracker.md`

```markdown
# Issue tracker
- Tracker and project, e.g. GitHub Issues in this repository, or a local
  `.scratch/` directory.
- Commands to list, read, create, comment, close, link dependencies.
- Labels or states that mean "waiting on the owner", "blocked", "in progress".
- Reconciliation: what to record when work linked to an issue is committed or
  shipped, and the rule to close only completed scope.
- Language for issue text.
```

## Workaround marks

Mark every workaround for someone else's bug or missing feature where it lives:

```
UPSTREAM(owner/repo#123): what this works around; remove when <condition>.
```

A lint rule should require the link on every mark. Then the list of workarounds
to revisit after a dependency update is a `grep`, not a memory. Pins kept for a
reason are listed in `checks.md` or next to the pin itself.

## Skills with a pack skill's name

A pack skill installed for the user and a project skill with the same name do
not combine:

- Claude Code runs the user-level one: enterprise beats personal, personal beats
  project ([Claude Code docs](https://code.claude.com/docs/en/skills), "Resolve
  skills that share a name"). A project's own `push` stops running the moment
  the pack's `push` is installed.
- Codex does not merge two skills that share a `name`, and both can appear in
  skill selectors; which one it picks is not documented
  ([Codex docs](https://learn.chatgpt.com/docs/build-skills)).

So install a pack skill that a project also has only after that project's copy
is removed and the `docs/agents/*.md` files the pack skill reads are in place
(for `push`, `release` and `finish`: `publishing.md`). `bin/install` reports
each such project skill as a shadow and holds the pack skill back until then.
