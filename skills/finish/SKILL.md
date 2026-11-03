---
name: finish
description: "Use when asked to take work all the way out in one go: commit, push, merge, clean up, install or deploy."
---

# Finish

One request, the whole chain. Each step runs under its own skill and rules; this
skill only orders them and stops at the first failure.

1. **Commit** (`commit`): all of this task's work.
2. **Land**: if the work sits on a task branch or worktree, bring it onto the
   destination the way `docs/agents/publishing.md` says (rebase and fast-forward,
   or the project's land command). Do not create merge commits the contract
   does not ask for.
3. **Push** (`push`): the whole outgoing chain, CI to a final result.
4. **Release** (`release`): only if the user asked for one or the contract makes
   it part of shipping this kind of change.
5. **Clean up** (`cleanup`): this task's merged branches, worktrees, servers and
   temporary files. Leave anything not yours.
6. **Install or deploy**: the steps under "after publish" in the contract, each
   only after the previous one succeeded. Skip it when the contract has none.

Steps the user left out of the request stay out; a chain that lists only
"commit and push" ends after step 3.

When a step fails, stop there. Fix what belongs to this task and continue; for
anything else report the state and the decision needed. Never skip a failed step
to reach the next.

## Report

Lead with the outcome in one line, then:

- **Before → after**: refs and SHAs that moved, versions, what is installed or
  deployed now.
- **Risk**: is it reversible, and how (revert commit, previous version, rollback
  command); what else it touches (dependents, users, data).
- **Not verified**: anything checked only partly or not at all, such as behavior
  on a real device, a CI job that could not run, a deploy without a smoke check.
- **Left**: what remains and who has to act.
