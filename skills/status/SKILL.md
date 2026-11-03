---
name: status
description: Use when asked what is in flight, blocked or waiting on the user. Read-only snapshot of tracker, branches, worktrees, CI and machine slots.
---

# Status

Read only. Change nothing, start nothing, kill nothing.

## Gather

Collect what exists; skip a source that is not set up and say it was skipped.

- **Tracker**: open and in-progress items assigned to the user or to agents, via
  `docs/agents/issue-tracker.md`. Note items waiting on the owner.
- **Git**: for each repository in scope, current branch, ahead/behind against
  its upstream, uncommitted changes, unpushed commits, stashes, branches not
  merged into the base, worktrees.
- **Lanes**: if a lane tool is installed (for example `lanefather list`), its
  running and queued lanes with their claims.
- **Machine**: `slotfather status` for who holds and who waits for slots.
- **CI**: the latest run on each published branch and its result.
- **Sessions**: other agent sessions you can list, and what each is doing.

Scope: the current repository unless the user names more. "Everything" means
every repository the user works in that you can find from here.

## Report

Four groups, most urgent first inside each:

- **Waiting on you**: decisions, approvals, reviews, owner checks. Each with the
  question and a recommended answer.
- **Blocked**: what is stuck, on what, and the next step that would unblock it.
- **Running**: work in progress, with owner (session, lane, person) and what it
  holds (files, slots, branch).
- **Loose ends**: unpushed commits, unmerged branches, dirty worktrees, red CI,
  stale leases. Suggest `cleanup` or `push` where they apply.

One line per item, links to issues, runs and branches instead of retelling them.
End with the single most useful next action.
