---
name: orchestrate
description: Use when asked to orchestrate, run implement-spec, or build several tickets in parallel with implementer agents. One worktree lane per ticket chain, blind cross-model review, one writer for the main branches.
---

# Orchestrate

A **lane** is a registered unit of repository work, with **claims** for the paths
it expects to change. An implementer normally works on it in a worktree; the lane
has its own lifecycle through checks, integration, review and cleanup. It can make
several Slotfather requests, which lease machine capacity only for executions.

Read `docs/agents/orchestration.md`: the lane tool, the report labels, the
review policy, the owner queue and the additions to the implementer brief.
Report missing required project files and recover the facts from the task's
available instructions; do not guess a project's tool or publishing policy.
Defaults apply to omitted sections. With a lane tool, drive every step through
it. When the project has none, use worktrees, branches
and `gh`, and keep the bookkeeping in a notes file. Put lane worktrees where
`docs/agents/publishing.md` says, else as `<repo>-<lane>` next to the
repository, so `cleanup` finds them.

## Plan

1. Read the spec and every ticket with its blockers. The **frontier** is the
   open tickets whose blockers are closed. Keep an
   [accepted-requirement record](references/batch-verification.md#accepted-scope)
   for the batch and add follow-ups as they are accepted.
2. Create an integration branch in its own worktree. Only you write to it, and
   only you move the main branches, through the promote tool if there is one.
3. Budget lanes. A usage limit stops every agent at once, so give one agent a
   chain of related tickets instead of one agent each, and run fewer lanes when
   limits are low. Lanes whose claims overlap run in sequence; land a prefactor
   that moves files before lanes that edit around it.

## Run

4. **Launch** each lane in the background with the `implement` role's model:
   a short prompt with ticket links, base branch, claims, which lanes work
   nearby, [references/implementer.md](references/implementer.md), and the
   project's brief additions and report labels. Point at the spec and tickets;
   do not paste them. Register every lane with its ticket (`--ticket`).
5. **Land** a lane when it reports green: merge it into the integration branch,
   run a quick smoke on the merge, send a red smoke to the lane whose change
   broke it. Resolve trivial conflicts yourself, real ones in the lane.
   The merge message ends with `Fixes #N`, so the ticket closes only when the
   merge reaches the default branch. After a green smoke, label the ticket
   `integrated` (create it if missing: green, "Done and landed in the
   integration/dev branch; not yet on main or released") and comment the merge
   SHA, the integration branch, whether it is pushed (a SHA origin lacks is
   "local only" and not linked), the checks it passed and the preview to try
   it on. Where the lane tool does this (Lanefather's `[tickets]`), read its
   output instead.
6. **Review** each landed lane once (`cross-review`), when and how the project's
   review policy says, else right after the land: the
   reviewer sees the diff, ticket and standards, never the lane's report. It
   runs beside the next lands. One round of fixes in the same lane, every
   finding marked fixed or rejected; nobody reviews the fix.
7. **Recompute the frontier** after every land and launch what became ready.

## Batch

8. **Gate once per batch**: the full gate on the batch tip, not per lane. Red:
   find the lane by running the failed suites on each merge. The batch moves to
   the everyday branch only when it is green and every review is resolved.
   Cross-cutting migrations and legacy removals use the
   [collect-all verification record](references/batch-verification.md#cross-cutting-verification)
   before fixes are distributed.
9. **Questions** from lane reports go to the owner queue the project names,
   else to the owner in one message: numbered, each with the default the lane
   already implemented. Record answers on the
   spec issue, not in session notes. Settle a question yourself when the
   default is clearly right, stays inside approved scope and is cheap to
   reverse (lane order, skipping an optional item whose gain is marginal), and
   report it in one line: the owner should only see real trade-offs in look,
   behaviour, public names, cost or taste.
10. **After a limit stop**, resume only agents one step from done; commit the
    rest as WIP on their branch and restart them fresh from it.

## Finish

Reconcile every ticket and accepted requirement with commits and checks,
[read back tracker changes](references/batch-verification.md#tracker-readback),
publish only on an explicit push (`push`), and clean up lanes and
worktrees (`cleanup`).

After a release, or a promote to the default branch, comment the version or
the main SHA on each ticket it closed, found from the `Fixes #N` lines in the
range. A ticket whose landed work leaves known follow-ups keeps them as
checklist items or linked issues; `integrated` still means the accepted scope
landed.
