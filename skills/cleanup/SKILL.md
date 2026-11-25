---
name: cleanup
description: "Use when asked to clean up after work: merged branches, stale worktrees, leftover folders next to a repository, stray processes. Deletes only what is provably merged or yours; asks about the rest."
---

# Cleanup

Inventory first, delete second, ask about everything in between.

## Inventory

Fetch with `--prune`, then list:

- **Branches** (local and remote) against `origin/<base>` (`docs/agents/publishing.md`,
  else default branch): merged by ancestry (`git branch --merged`), merged by
  content (`git cherry` has no `+` lines — squash/rebase case), or unmerged with
  commit count and last date.
- **Worktrees** (`git worktree list`): branch, merged state, uncommitted changes,
  and running processes inside them, including `<repo>/.claude/worktrees/` and
  temp-dir worktrees (`/tmp`, `$TMPDIR`, `/var/folders`). Remove tool-owned
  worktrees through the tool named in `docs/agents/publishing.md`. Also check
  `<repo>/.claude/worktrees/` for orphans (`.git` file pointing at a worktree git
  no longer knows) and leftover folders.
- **Folders next to the repository** (`<repo>-*` in parent dir): classify each as
  a repo worktree (treat as above), an orphan (dangling `.git` file or
  `git worktree prune --dry-run` hit), a clone (own `.git` dir — check unpushed
  commits and changes), or a plain folder (size, last change, 1-line contents).
- **Archives** from earlier cleanups (see Keep) older than 30 days.
- **Processes** (port and command) and **temporary directories** this task started.

## Delete

Safe without asking:

- branches whose every commit is in `origin/<base>`, and their clean, idle worktrees;
- processes and temporary files this task started.

Never without the user's yes:

- anything with uncommitted changes or unpushed commits;
- anything another session or agent may own: a worktree with a running process,
  a branch you did not create, a process you did not start;
- machine-wide locks and leases (for example `slotfather` leases) held by someone
  else, even if they look stale; the tool reaps dead holders itself.

Always ask about plain folders and clones next to the repository. Remove
worktrees with `git worktree remove`, never `rm -rf`. If git unregisters a
worktree but leaves a folder behind (ignored files: dependencies, generated
media), compare what remains against the main checkout and branch; delete only
when nothing is unique, otherwise report it. Delete merged branches with
`git branch -d`; use `-D` only for content-merged branches just verified with
`git cherry`.

## Keep

When the user agrees to remove something with unique work (uncommitted changes,
unmerged branches), save it first: `git diff` as a patch and a `git bundle` of
the branches under `${XDG_STATE_HOME:-$HOME/.local/state}/cleanup/<repo>/<date>/`,
never next to the repository. Report the path; a later cleanup offers to delete
it after 30 days.

## Report

A table of what was removed, then a table of what remains with the reason and a
recommendation for each (delete, keep, merge first). Ask about those in one
question.
