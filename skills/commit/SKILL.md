---
name: commit
description: Create local Git commits for the work of the current task, safely in a working tree that other agents share. Use for commit requests such as "commit", "коммить", "закоммить", or when an authorized push needs commits first. Editing a skill named commit is not a commit request.
---

# Commit

A commit request is local only; publishing needs a push request.

## Scope

A bare request covers all uncommitted work of this task, recovered from the whole
conversation: earlier accepted requirements, their tests, docs and changelog entry,
not just the latest edit. Only an explicit limit from the user narrows it.

Inventory before staging. For each requirement of the task, say whether it is
already committed, in this candidate, or left out and why. Leave out work that
belongs to another task, judged by purpose and owner, not by age.

## The tree is shared

Other sessions may be editing this checkout right now.

- Never stash, reset, restore, or check out files you did not change; never
  switch branches. Read a committed version with `git show HEAD:<path>`.
- Stage explicit paths. Look at every untracked file before adding it.
- A file that mixes your hunks with someone else's: stage only your hunks.
- If the real index holds someone else's staging, build the commit in a temporary
  index (`GIT_INDEX_FILE`) initialised from `HEAD`, and leave the real one as found.
  Details: [references/shared-tree.md](references/shared-tree.md).

## Validate and commit

- Read the full staged diff. Run the checks `docs/agents/checks.md` names for
  this change, on the staged tree, not a working tree that hides missing files.
  Reuse a result whose inputs have not changed.
- Before committing, confirm `HEAD` is still the parent you built on. If it moved,
  rebuild on the new parent.
- Message: what behavior changed, in the repository's convention. When a bug
  was diagnosed, name the cause that turned out to be true.

## Report

Hashes and subjects, what each covers, the checks run, and every change group
left in the tree with its paths and why. Say so when the tree is clean. If task
work remains uncommitted or unvalidated, call the request partial.

Continue to `push` only when publication was asked for.
