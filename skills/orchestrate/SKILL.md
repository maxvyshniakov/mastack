---
name: orchestrate
description: Use when asked to orchestrate, run implement-spec, or build several tickets in parallel with implementer agents. One worktree lane per ticket chain, blind cross-model review, one writer for the main branches.
---

# Orchestrate

A **lane** is a registered unit of work with **claims** for the paths it expects
to change. Each implementer uses its own worktree; Slotfather leases machine
capacity only for executions.

Read `docs/agents/orchestration.md` (lane tool, report labels, review policy,
owner queue, brief additions). Report missing project files; never guess tool or
publishing policy. Drive every step through the lane tool when present, else
worktrees, branches, `gh`, and a notes file. Default worktree path when
`docs/agents/publishing.md` names none: `<repo>/.claude/worktrees/<name>`.

## Plan

1. Read the spec and tickets with their blockers. The **frontier** is open
   tickets whose blockers are closed. Keep an
   [accepted-requirement record](references/batch-verification.md#accepted-scope).
2. Create an integration branch in its own worktree. Only you write to it, and
   only you move the main branches (via the promote tool if one exists).
3. **Budget lanes.** Run fewer lanes when usage limits are low. Reuse a warm
   agent when idle time and context stay within `warm_idle_minutes` and
   `warm_context_tokens` under `[providers.<family>]` in `models.toml` and the
   next task touches the same code; otherwise start fresh from a WIP commit.
   Sequence overlapping claims; land a prefactor before lanes editing around it.

## Launch

Run `<this skill's directory>/scripts/role <role>` (with
`[--harness auto|claude|codex|t3]`, `--family`, or `--exclude-family` to route
around exhausted providers) and pass its model and reasoning option on **every**
launch (implement, fix rounds, scouting):

- **Claude Code (`Agent`)**: pass `model` and `effort`; include `Role: <role>`
  so `hooks/agent_role.py` fills them if omitted.
- **Codex (`codex exec`)**: use `[cli.codex].run`; for read-only scouting add
  `-s read-only -C <repo> --output-last-message <file> "<task>" < /dev/null`
  in the background (`< /dev/null` prevents stdin hang).
- **T3 Code / Antigravity (`delegate_task`)**: set `target.model` to `id`,
  `target.options.<option>` to `effort`, and include `Role: <role>` in `task`.
  Claude Code hooks only fire on Claude-backed sessions (not Antigravity or
  Codex), so enforce model/option selection and bounded output via the brief.

**Scouting.** Use `scripts/role scout` for read-only mapping/grepping; send
judgment or design proposals to `scripts/role design`.

## Run

4. **Launch lanes.** Register each lane with `--ticket` first so the brief names
   its worktree. Point at spec and tickets; do not paste them. Pre-fill every
   command with lane id and paths so implementers never spend turns on `--help`
   or polling `lanefather list`.

   ```text
   Role: implement
   Tickets: <links, in order>. Spec: <link>.
   Lane <id>, registered. Base: <integration branch>. Claims: <globs>.
   Nearby lanes: <id: claims>, ...
   Worktree: <absolute path>. Branch: <lane branch>.
   Focused checks: <scripts and filters for what this lane changes>
   Check: mine | yours, once before hand-back: <lane check command>
   Hand back: commit, green focused checks (and lane check if yours), return report and stop.
   After you: I run the lane check and review together and send both results once; then I land (<land command>).
   Read <this skill's directory>/references/implementer.md, then:
   <project brief additions>. Report labels: <labels>.
   ```

5. **Check and review before land.** On hand-back (committed tree, green focused
   checks), start the lane check and blind
   [cross-review](../cross-review/SKILL.md#one-round-of-fixes) together: give
   the reviewer only the diff, ticket, standards,
   [reviewer brief](../cross-review/references/reviewer-brief.md), and the
   report's `Least sure` places — never the lane report or conclusions. Triage
   finished reviews on arrival before later lands, sending check failures and
   findings to the same implementer once; it fixes, final check runs once, and
   you land. When fixing small findings yourself, run targeted local `lint` +
   touched unit test (<10s) before `lanefather check`. Wait for completion
   notices; never poll `lanefather list`.
6. **Land** when the check is green and every finding is marked fixed or
   rejected:
   - Merge integration tip into the lane before final check, then merge into
     integration. Route red smoke to the breaking lane; resolve trivial
     conflicts yourself, real ones in the lane.
   - End the merge message with `Fixes #N`. After green smoke, label the ticket
     `integrated` (create if missing) and comment merge SHA, branch, push status
     (never link an unpushed SHA), checks passed, and preview (or read
     Lanefather `[tickets]` output). Routine project-tracker bookkeeping
     (evidence comments, follow-up tickets) needs no permission.
   - **Unreviewed landed lanes** with findings take one fix round via the
     fix-round path (`lanefather review <id> --fix-lane`, or
     `start <fix-id> --fix-of A,B,C`), never plain `start` (which loops
     reviews); see [One round of fixes](../cross-review/SKILL.md#one-round-of-fixes).
     Reuse the warm implementer per `[providers.<family>]`, else start fresh
     with findings and diff. On any stray fix-round review, mark findings
     `rejected: fix round, not reviewed again (one review per lane)` unless a
     finding is a verified P0 with a failing falsifier (flag and fix before land
     or promote).
   - Run `lanefather done` as soon as the last finding is marked so worktrees do
     not fill disk.
7. **Recompute the frontier** after every land and launch ready tickets.

## Batch

8. **Gate once per batch** on the batch tip (not per lane); bisect red suites
   across merges. Move to the everyday branch only when green and all reviews
   are resolved; push small batches (3–5 lanes) to the everyday branch per
   `docs/agents/publishing.md` ([push](../push/SKILL.md)) and report in one line
   (no owner wait unless `publishing.md` says so). Release branches, releases,
   guarded publishes, another project's tracker, and premature closes remain
   owner-authorized per `publishing.md` and [release](../release/SKILL.md).
   Cross-cutting migrations use
   [collect-all verification](references/batch-verification.md#cross-cutting-verification).
9. **Questions.** Filter every implementer `Questions` item and reviewer lead
   through [Owner's decisions](../cross-review/SKILL.md#owners-decisions) —
   never copy reviewer `W*` leads mechanically into a questions list; record
   owner answers on the spec issue.
10. **After a limit stop**, resume only agents one step from done; commit the
    rest as WIP on their branch and restart fresh.

## Finish

Reconcile tickets and accepted requirements with commits and checks,
[read back tracker changes](references/batch-verification.md#tracker-readback),
and clean up lanes and worktrees ([cleanup](../cleanup/SKILL.md)).

Route non-code report lines before the batch report:

- `Least sure`: to the lane's reviewer (step 5), else check yourself.
- `Garden` and review `Follow-ups`: fold `small` same-root items into the fix
  round; deduplicate `lane` items against open issues and file with their
  `Proof / Direction / Verify` body; drop noise. Record `Garden yield` (kept vs
  dropped) in the batch report.
- `Friction`: fix owned brief/doc/skill now and warn running lanes; file tool
  defects in the tool's tracker.
- `Upstream`: file in owned dependency tracker; draft for owner elsewhere.
- Review's "should have been caught by": promote recurring classes to a check or
  reviewer rule, not just a ticket.

End the batch report with routing counts and the last run dates of
`orchestration-audit` (weekly) and `test-audit` (monthly); run any overdue audit
or say why not. After a release or default-branch promote, comment the version
or main SHA on each closed ticket (`Fixes #N`).
