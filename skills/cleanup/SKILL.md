---
name: cleanup
description: Find and remove leftovers - merged branches, stale worktrees, hanging dev servers and background processes, temporary directories - deleting only what is provably merged or yours and asking about the rest. Use for "cleanup", "почисти", "невлитые ветки", "убери за собой".
---

# Cleanup

Inventory first, delete second, ask about everything in between.

## Inventory

Fetch with `--prune`, then list:

- **Branches**, local and remote, with their state against the base branch
  (`origin/<base>` from `docs/agents/publishing.md`, else the default branch):
  merged by ancestry (`git branch --merged`), merged by content (`git cherry`
  shows no `+` lines, the squash or rebase case), or unmerged with commit count
  and last date.
- **Worktrees** (`git worktree list`): branch, merged state, uncommitted changes,
  and whether a process is running inside it.
- **Processes**: dev servers and background jobs this task started, with port
  and command.
- **Temporary directories** this task created.

## Delete

Safe without asking:

- branches whose every commit is in `origin/<base>`, and their worktrees when
  those are clean and idle;
- processes and temporary files this task started.

Never, without the user's yes:

- anything with uncommitted changes or unpushed commits;
- anything another session or agent may own: a worktree with a running process,
  a branch you did not create, a process you did not start;
- machine-wide locks and leases (for example `slotfather` leases) held by
  someone else, even if they look stale; the tool reaps dead holders itself.

Remove worktrees with `git worktree remove`, never `rm -rf`. Delete merged
branches with `git branch -d`; reach for `-D` only for content-merged branches
you just verified with `git cherry`.

## Report

A table of what was removed, then a table of what remains with the reason and
a recommendation for each (delete, keep, merge first). Ask about those in one
question.
