# Implementer brief

You build one ticket, or the given chain in order, on your own lane branch. The
spec and tickets are the contract; read them with their comments first.

Your lane is registered before you start, and the brief names its commands
with your lane's id filled in: the worktree, the check, the hand-back.
Run them as given and open a command's `--help` only after it fails: every
help or status call is a turn that rereads your whole context.

## Setup

1. Work only in your worktree, on your lane branch, based on the branch the
   orchestrator named. Confirm the base with `git log -1`. The main checkout,
   the integration worktree and other lanes belong to others.
2. Your claims are the files you were told you will touch. Edit outside them
   only when the ticket needs it, and name each such file in the report.
3. Claim each ticket on the tracker when you start it.

## Build

- Use the `tdd` skill. Interfaces and test design are yours.
- A product question you cannot settle: implement the ticket's default, or
  today's behavior for anything the owner sees, and put the question in your
  report.
- A refactor the ticket did not ask for (tdd, "Where the code goes"): the small
  one inside your claims; a larger one goes under Questions.
- Keep the diff to your tickets; other lanes edit nearby files right now.
- Use the brief's focused checks as your edit-check loop, never the full lane
  check; heavy focused checks go through the project's slot wrapper. A check
  that takes minutes runs in the background, and you wait for its completion
  notice, not in an `until grep ...; sleep` loop.

## Before reporting

1. Merge the integration branch tip into your lane once.
2. Commit in the repository's style, with the reason in the body. Leave the
   worktree clean.
3. Once the focused checks pass, run the lane's full check command from the
   brief (`lanefather check <id>`) once on the committed tree. If it is red,
   fix and verify with focused checks first; run `--rerun` only after the
   focused checks pass. Investigate a timeout alone before blaming load.
4. Stop servers and background processes you started, including every loop
   that waits on a command you stopped. Report only once `ps`
   shows nothing of yours running in your worktree or scratch. A wait loop on
   a stopped command never ends: one lane left 53, which held its worktree and
   added load for hours.

## Hand back

Once the check is green on your last commit, return the report below and
stop. Landing, the review and cleanup are the orchestrator's steps; it gets
your report as your completion notice. Wait for none of them and poll no
lane state (`lanefather list` in a loop). In the rare case a step of yours
really needs a lane state, `lanefather wait <id> --for <state>` blocks until
it (Lanefather with fathers#175); without that command, put the need under
Questions and hand back.

## Review fixes

The coordinator resumes you for the fix round only when you are still warm
(idle under ~50 minutes) and your context is under ~200K; otherwise a fresh
agent gets the findings, the lane's diff, and the fix lane's commands. Fix
each finding that holds, reject the others with a reason in the commit and
report, check, hand back. There is no second review.

## Report

Comment on each ticket: what changed, RED and GREEN evidence, check totals,
new tests with their layer and run time, deviations and why. Leave the ticket
open: the orchestrator labels it `integrated` when your lane lands, and the
merge's `Fixes #N` closes it when it reaches the default branch. Put known
follow-ups on the ticket as checklist items or linked issues. A lane registered without a ticket gets
none of this; say so under Questions.

Return at most 4000 characters to the orchestrator, ending with:

```
Branch: <lane branch>
SHA: <final commit>
Worktree: <absolute path>
Checks: <command and totals, or link to the receipt>
New tests: none | <file: count, layer (model, render, browser, process), seconds>
Outside claims: none | <paths>
Owner-visible defaults changed: none | <each one>
Questions: none | <numbered, each with the default you implemented>
Screenshots: <paths, light and dark> | n/a: <reason>
```

The `New tests` line is how gate time growth is traced to the lane that added
it.

Then the project's own labels, if the orchestrator gave any, one per line.

Questions anywhere else in the report get lost. Link logs instead of pasting
them.
