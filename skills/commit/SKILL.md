---
name: commit
description: Use when asked to commit, or when an authorized push needs commits first. Stages only this task's files explicitly without disturbing unfamiliar edits. Editing a skill named commit is not a commit request.
---

# Commit

Local only; continue to [push](../push/SKILL.md) only when publication was asked
for (or an orchestrator pushes a green batch to the everyday branch).

## Scope

A bare request covers all uncommitted work of this task from the whole
conversation — earlier accepted requirements, tests, docs and changelog, not
just the latest edit. Only an explicit limit from the user narrows it.

Inventory before staging: for each requirement, state whether it is already
committed, in this candidate, or left out and why. Leave out other tasks' work
by purpose and owner, not age.

## Checkout hygiene

The user may have local edits in the primary checkout.

- Stage explicit paths (`git add -- <paths>`); never `git add -A` or `git add .`.
  Inspect every untracked file before adding it.
- Never `stash`, `reset`, `restore`, or `checkout --` unfamiliar files, and never
  switch branches over dirty files. Read committed versions via `git show HEAD:<path>`.
- If the index already holds unexpected staged changes or a file mixes your hunks
  with unfamiliar edits, stop and ask the user instead of building temporary
  indexes or plumbing blobs (`GIT_INDEX_FILE`, `hash-object`, `update-index`).

## Validate and commit

- Read the full staged diff. Run the checks `docs/agents/checks.md` names for
  this change on the staged tree — not a working tree whose untracked or
  unstaged files can mask missing files or imports (when unfamiliar files in the
  working tree could hide a gap, check the staged tree in a temporary detached
  worktree under `.claude/worktrees/`, and reuse a result whose inputs have not
  changed).
- Message: behavior changed, in repo convention; for diagnosed bugs, name the
  verified root cause.

## Report

Hashes and subjects, what each covers, checks run, and every change group left
in the tree with paths and why (or note the tree is clean). Call the request
partial if task work remains uncommitted or unvalidated.
