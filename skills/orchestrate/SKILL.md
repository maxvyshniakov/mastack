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

**Scouting.** Before you hand off a read-only scouting task (map X, find where
Y lives, list the callers of Z), run `<this skill's directory>/scripts/role
scout`; it picks Sol while Codex has quota, so reading stops spending the
Claude limit. Sol: its `run` command with `-s read-only -C <repo>
--output-last-message <file> "<task>" < /dev/null` in the background, then
read the file; without `< /dev/null` `codex exec` waits on stdin. Sonnet: the
Agent tool with `model: sonnet`. A task that asks for judgment or a proposal
(a design, what should replace X) goes to `scripts/role design` instead.

## Run

4. **Launch** each lane in the background with the model and effort
   `<this skill's directory>/scripts/role implement` prints (it reads the
   live quotas). Register the lane with its ticket (`--ticket`) first, so the
   brief can name its worktree. Point at the spec and tickets; do not paste
   them. Fill every command with the lane's id and paths: implementers spent
   hundreds of turns on `lanefather --help` and polling `lanefather list`
   for steps that were yours, each turn rereading their whole context.

   ```text
   Tickets: <links, in order>. Spec: <link>.
   Lane <id>, registered. Base: <integration branch>. Claims: <globs>.
   Nearby lanes: <id: claims>, ...
   Worktree: <absolute path>. Branch: <lane branch>.
   Focused checks: <the scripts and filters for what this lane changes>
   Check (once, before hand-back): <the lane's check command, e.g. lanefather check <id>>
   Hand back: commit, green focused checks, then one green lane check on the
   committed tree, then return your report and stop.
   After you: I land the lane (<land command>), its review runs, and the
   findings come back to you once, in the fix lane.
   Read <this skill's directory>/references/implementer.md, then:
   <the project's brief additions>. Report labels: <labels>.
   ```
5. **Land** a lane when it reports green. The report reaches you as the
   agent's completion notice; wait for that, not on `lanefather list`. Merge
   it into the integration branch, run a quick smoke on the merge, send a red
   smoke to the lane whose change broke it. Resolve trivial conflicts
   yourself, real ones in the lane.
   The merge message ends with `Fixes #N`, so the ticket closes only when the
   merge reaches the default branch. After a green smoke, label the ticket
   `integrated` (create it if missing: green, "Done and landed in the
   integration/dev branch; not yet on main or released") and comment the merge
   SHA, the integration branch, whether it is pushed (a SHA origin lacks is
   "local only" and not linked), the checks it passed and the preview to try
   it on. Where the lane tool does this (Lanefather's `[tickets]`), read its
   output instead. Writes to the project's own tracker are bookkeeping, not
   publishing: post the evidence comments the lane tool asks for, file
   follow-up tickets and correct your own comments without asking, then link
   them in the report. Push, release, publish and closing a ticket before its
   fix ships follow `publishing.md`; another project's tracker needs the
   owner's yes first.
6. **Review** each landed lane once (`cross-review`), when and how the project's
   review policy says, else right after the land: the
   reviewer sees the diff, ticket and standards, never the lane's report. It
   runs beside implementation. Triage findings as soon as the review finishes
   (or the lane list/stop hook reports them), while the diff is fresh; the
   [Lanefather gate](https://github.com/maxvyshniakov/fathers/issues/177) enforces
   this before further lands. Every finding is marked fixed or rejected before
   promotion or release. One round of fixes, every finding marked fixed
   or rejected, started only through the lane tool's fix-round path:
   `lanefather review <id> --fix-lane` for one lane, `lanefather start <fix-id>
   --fix-of A,B,C` for the findings of several (fathers#174; until it ships,
   one `--fix-lane` per lane). A plain `start` is an ordinary lane, which
   `land` reviews: batched fix lanes started that way chained six and seven
   rounds deep. Nobody reviews the fix. A review of it that runs anyway opens
   no new round and no new fix lane: mark each of its findings
   `rejected: fix round, not reviewed again (one review per lane)` so the
   lane finishes. Finish the lane in
   the lane tool (Lanefather's `done`) as soon as its last finding is marked:
   it removes only merged worktrees, branches and scratch, and finished lanes
   left for batch end fill the disk until the lane tool refuses new lanes.
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
