---
name: orchestrate
description: Build a spec's tickets in parallel lanes - one implementer agent per ticket chain, each with file claims in its own worktree - with a blind review by another model, one round of fixes, one gate per batch and a single writer for the main branches. Use for "orchestrate", "оркестрируй", "run these tickets in parallel".
---

# Orchestrate

A **lane** is one implementer agent in its own worktree, working one ticket or a
chain of related tickets, with **claims**: the files it expects to touch. If a
lane tool is installed (for example `lanefather`), drive every step below
through it. Otherwise use worktrees, branches and `gh`, and do the bookkeeping
in a notes file.

## Plan

1. Read the spec and every ticket with its blockers. The **frontier** is the
   open tickets whose blockers are closed.
2. Create an integration branch in its own worktree. Only you write to it, and
   only you move the main branches, through the promote tool if there is one.
3. Budget lanes. A usage limit stops every agent at once, so give one agent a
   chain of related tickets instead of one agent each, and run fewer lanes when
   limits are low. Lanes whose claims overlap run in sequence; land a prefactor
   that moves files before lanes that edit around it.

## Run

4. **Launch** each lane in the background with the `implement` role's model:
   a short prompt with ticket links, base branch, claims, which lanes work
   nearby, and [references/implementer.md](references/implementer.md). Point at
   the spec and tickets; do not paste them.
5. **Land** a lane when it reports green: merge it into the integration branch,
   run a quick smoke on the merge, send a red smoke to the lane whose change
   broke it. Resolve trivial conflicts yourself, real ones in the lane.
6. **Review** each landed lane once with the `review` role (`cross-review`): the
   reviewer sees the diff, ticket and standards, never the lane's report. It
   runs beside the next lands. One round of fixes in the same lane, every
   finding marked fixed or rejected; nobody reviews the fix.
7. **Recompute the frontier** after every land and launch what became ready.

## Batch

8. **Gate once per batch**: the full gate on the batch tip, not per lane. Red:
   find the lane by running the failed suites on each merge. The batch moves to
   the everyday branch only when it is green and every review is resolved.
9. **Questions** from lane reports go to the owner in one message, numbered,
   each with the default the lane already implemented. Record answers on the
   spec issue, not in session notes.
10. **After a limit stop**, resume only agents one step from done; commit the
    rest as WIP on their branch and restart them fresh from it.

## Finish

Reconcile every ticket and accepted requirement with commits and checks, update
the tracker, publish only on an explicit push (`push`), and clean up lanes and
worktrees (`cleanup`).
