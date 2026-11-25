---
name: finish
description: "Use when asked to take work all the way out in one go: commit, push, merge, clean up, install or deploy."
---

# Finish

One request, the whole chain. Each step runs under its own skill and rules; this
skill orders them and stops at the first failure.

1. **Commit** ([commit](../commit/SKILL.md)): all of this task's work.
2. **Land**: bring task-branch or worktree work onto the destination per
   `docs/agents/publishing.md` (rebase and fast-forward, or the project's land
   command). Never add merge commits the contract does not ask for.
3. **Push** ([push](../push/SKILL.md)): the whole outgoing chain, CI to a final result.
4. **Release** ([release](../release/SKILL.md)): only if asked or required by the contract.
5. **Clean up** ([cleanup](../cleanup/SKILL.md)): this task's merged branches, worktrees,
   servers and temporary files. Leave anything not yours.
6. **Install, deploy, restart**: run the contract's steps in order, each only
   after the previous succeeded. Skip when the contract has none; a request for
   only an install or restart runs just this step.

Leave out steps the user omitted ("commit and push" stops after step 3).

On failure, stop there: fix what belongs to this task and continue, otherwise
report the state and decision needed. Never skip a failed step to reach the next.

## Report

Lead with the outcome in one line, then:

- **Before → after**: refs and SHAs that moved, versions, what is installed or
  deployed now.
- **Risk**: reversibility and rollback (revert commit, previous version, rollback
  command), and blast radius (dependents, users, data).
- **Not verified**: anything checked partly or not at all (real device, skipped
  CI job, deploy without smoke check).
- **Left**: what remains and who has to act.
