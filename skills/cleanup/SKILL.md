---
name: cleanup
description: "Use when asked to clean up after work: merged branches, stale worktrees, leftover folders next to a repository, stray processes. Deletes only what is provably merged or yours; asks about the rest."
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
- **Folders next to the repository**: every directory in its parent whose name
  starts with the repository's name (`<repo>-*`). Classify each one:
  - a worktree of this repository: treat it as above;
  - an orphan: a `.git` file pointing at a worktree git no longer knows, or an
    entry `git worktree prune --dry-run` would drop;
  - a clone: its own `.git` directory; check for unpushed commits and changes;
  - a plain folder (archives, screenshots, backups): size, last change, and
    what is inside in one line.
- **Archives** from earlier cleanups (see Keep) older than 30 days.
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

Plain folders and clones next to the repository are always asked about, never
assumed to be leftovers. Remove worktrees with `git worktree remove`, never
`rm -rf`. If git unregisters a worktree but leaves its folder behind (ignored
files: dependencies, generated media), compare what is left with the main
checkout and the branch; delete the folder only when nothing in it is unique,
otherwise report it. Delete merged branches with `git branch -d`; reach for
`-D` only for content-merged branches you just verified with `git cherry`.

## Keep

When the user agrees to remove something that holds unique work (uncommitted
changes, unmerged branches), save it first: `git diff` as a patch and a
`git bundle` of the branches, under
`${XDG_STATE_HOME:-$HOME/.local/state}/cleanup/<repo>/<date>/`, never next to
the repository. Say the path; a later cleanup offers to delete it after 30 days.

## Report

A table of what was removed, then a table of what remains with the reason and
a recommendation for each (delete, keep, merge first). Ask about those in one
question.
