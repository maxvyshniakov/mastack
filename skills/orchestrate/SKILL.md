---
name: orchestrate
description: Use when asked to orchestrate, run implement-spec, or build several tickets in parallel with implementer agents. One worktree lane per ticket chain, blind cross-model review, one writer for the main branches.
---

# Orchestrate

A **lane** is a registered unit of work with **claims** for the paths it expects
to change. An implementer works in its own worktree; Slotfather requests lease
machine capacity only for executions.

Read `docs/agents/orchestration.md` (lane tool, report labels, review policy,
owner queue, brief additions). Report missing project files; never guess tool or
publishing policy. With a lane tool, drive every step through it; without one,
use worktrees, branches, `gh`, and a notes file. Default worktree path when
`docs/agents/publishing.md` names none: `<repo>/.claude/worktrees/<name>`.

## Plan

1. Read the spec and every ticket with its blockers. The **frontier** is open
   tickets whose blockers are closed. Keep an
   [accepted-requirement record](references/batch-verification.md#accepted-scope)
   for the batch.
2. Create an integration branch in its own worktree. Only you write to it, and
   only you move the main branches (via the promote tool if one exists).
3. **Budget lanes.** Run fewer lanes when usage limits are low. Choose warm
   reuse vs fresh agent per task: reuse when idle and context stay within
   `warm_idle_minutes` and `warm_context_tokens` under `[providers.<family>]` in
   `models.toml` and the next task touches the same code; otherwise start fresh
   from a WIP commit. Sequence lanes with overlapping claims; land a prefactor
   before lanes that edit around it.

## Launch

Run `<this skill's directory>/scripts/role <role>` (with `--family` or
`--exclude-family` to route around exhausted providers) and pass its model and
reasoning option on **every** launch (implement, fix rounds, scouting):

- **Claude Code (`Agent`)**: pass `model` and `effort`; include `Role: <role>`
  so `hooks/agent_role.py` fills them if omitted.
- **Codex (`codex exec`)**: use `[cli.codex].run`; for read-only scouting add
  `-s read-only -C <repo> --output-last-message <file> "<task>" < /dev/null`
  in the background (`< /dev/null` prevents stdin hang).
- **T3 Code / Antigravity (`delegate_task`)**: set `target.model` to `id`,
  `target.options.<option>` to `effort`, and include `Role: <role>` in `task`.
  Claude Code hooks only fire for Claude-backed sessions (not Antigravity or
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

5. **Check and review before land.** When a lane hands back a committed tree
   with green focused checks, start its lane check and `cross-review` together.
   The reviewer gets the diff, ticket, standards,
   [reviewer brief](../cross-review/references/reviewer-brief.md), and the
   report's `Least sure` places to inspect — never the lane report or
   conclusions. Triage when both finish and send failures + findings to the same
   implementer in one message. It fixes, the final check runs once, and you
   land. Nobody reviews the fix. When you fix small review findings yourself,
   run targeted local `lint` + the touched unit test file (<10s) before
   launching `lanefather check`. Wait for completion notices, never poll
   `lanefather list`.
6. **Land** when the check is green and every finding is marked fixed or
   rejected:
   - Merge the integration tip into the lane before its final check, then merge
     into the integration branch. Route a red smoke to the breaking lane;
     resolve trivial conflicts yourself, real ones in the lane.
   - End the merge message with `Fixes #N` so the ticket closes when it reaches
     the default branch. After green smoke, label the ticket `integrated`
     (create it if missing) and comment merge SHA, branch, push status (never
     link an unpushed SHA), checks passed, and preview (or read Lanefather
     `[tickets]` output).
   - Project tracker bookkeeping (evidence comments, follow-up tickets) needs no
     permission; another project's tracker, pushes to release branches,
     releases, and premature closes follow `publishing.md`.
   - **Unreviewed landed lanes** that later get findings take one fix round via
     the lane tool's fix-round path (`lanefather review <id> --fix-lane`, or
     `start <fix-id> --fix-of A,B,C`), never a plain `start` (which triggers
     endless review loops). Reuse warm implementer per `[providers.<family>]`,
     else start fresh with findings and diff. If a review runs on fix work
     anyway, mark its findings `rejected: fix round, not reviewed again (one
     review per lane)`.
   - Finish each lane (`lanefather done`) as soon as its last finding is marked
     so worktrees do not fill disk.
7. **Recompute the frontier** after every land and launch ready tickets.

## Batch

8. **Gate once per batch** on the batch tip (not per lane). Red: bisect failed
   suites across merges. Move to the everyday branch only when green and all
   reviews are resolved; push small batches (3–5 lanes) to the everyday branch
   per `docs/agents/publishing.md` and report in one line (the everyday branch
   does not wait for the owner unless `publishing.md` says so). Release branch,
   releases, and guarded publishes stay the owner's command unless `publishing.md`
   grants standing permission (`release` skill). Cross-cutting migrations use
   [collect-all verification](references/batch-verification.md#cross-cutting-verification).
9. **Questions** must pass an explicit escalation gate before reaching the
   owner — never copy reviewer `W*` leads mechanically into a questions list.
   First run `cross-review`'s "Owner's decisions" (search session histories,
   `owner-turns.jsonl`, tracker, `AGENTS.md`, and git blame). Settle every
   cheap, reversible in-scope default or obvious follow-up yourself (apply or
   queue it and report in one line under **Decided**). Escalate to the owner
   ONLY when the choice is irreversible, requires explicit owner authorization,
   or is an expensive product/contract trade-off with no answer in docs or
   history; record answers on the spec issue.
10. **After a limit stop**, resume only agents one step from done; commit the
    rest as WIP on their branch and restart fresh.

## Finish

Reconcile tickets and accepted requirements with commits and checks,
[read back tracker changes](references/batch-verification.md#tracker-readback),
keep release-branch pushes and publishes to explicit owner requests (`push`,
`release`), and clean up lanes and worktrees (`cleanup`).

Route non-code report lines before the batch report:

- `Least sure`: to the lane's reviewer (step 5), else check yourself.
- `Nearby`, `Garden`, and review follow-ups: fold `small` same-root items into
  the fix round; deduplicate `lane` items against open issues and file them
  with their `Proof / Direction / Verify` body; drop noise. Record
  `Garden yield` (kept vs dropped) in the batch report.
- `Friction`: fix owned brief/doc/skill now and warn running lanes; file tool
  defects in the tool's tracker.
- `Upstream`: file in owned dependency tracker; draft for owner elsewhere.
- Review's "should have been caught by": promote recurring classes to a check or
  reviewer rule, not just a ticket.

End the batch report with routing counts and the last run dates of
`orchestration-audit` (weekly) and `test-audit` (monthly); run any overdue audit
or say why not. After a release or default-branch promote, comment the version
or main SHA on each closed ticket (`Fixes #N`).
