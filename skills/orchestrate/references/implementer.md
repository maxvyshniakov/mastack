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
- Keep tool output small (every tool result stays in context and is re-read on
  every later turn): read only a file's needed line range, not the whole file;
  cap search output (`grep -m`, `| head`); run `git show --stat` / `git diff
  --stat` before a full diff; never print a whole log — tail or grep it.
- Use the brief's focused checks as your edit-check loop, never the full lane
  check; heavy focused checks go through the project's slot wrapper. A check
  that takes minutes runs in the background, and you wait for its completion
  notice, not in an `until grep ...; sleep` loop.

## Before reporting

1. Merge the integration branch tip into your lane once.
2. Commit in the repository's style, with the reason in the body. Leave the
   worktree clean.
3. The brief says whose the lane's full check is. `Check: mine`: the
   orchestrator runs it beside the review once you hand back, so stop at
   green focused checks. `Check: yours`: run the brief's check command once on
   the committed tree. A red check: fix and verify with focused checks first,
   and `--rerun` only after they pass. Investigate a timeout alone before
   blaming load.
4. Stop servers and background processes you started, including every loop
   that waits on a command you stopped. Report only once `ps`
   shows nothing of yours running in your worktree or scratch. A wait loop on
   a stopped command never ends: one lane left 53, which held its worktree and
   added load for hours.

## Hand back

Once your part of the checks is green on your last commit, return the report
below and stop. The lane check (when it is the orchestrator's), the review,
landing and cleanup are the orchestrator's steps; it gets your report as your
completion notice. Wait for none of them and poll no
lane state (`lanefather list` in a loop). In the rare case a step of yours
really needs a lane state, `lanefather wait <id> --for <state>` blocks until
it; without that command, put the need under Questions and hand back.

## Review fixes

The review runs on your committed tree before the lane lands, beside the lane
check. Its findings and the check's failures come back to you once, in this
lane, while your context is warm. Each finding carries a falsifier: run it
first as a failing test; if it passes on your tree, reject the finding with
that test as the reason. Fix what holds at its cause, not with the reviewer's
proposed patch, one finding or root per commit. Merge the integration tip,
run the focused checks (and the lane check if the brief said `Check: yours`),
then hand back. There is no second review.

A fresh agent gets the same findings with the lane's diff when you are past
the provider's prompt-cache window or near compaction (per
`[providers.<family>]` in the model table), or when the lane had already
landed.

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
Nearby: none | <at most five, each with a size>
Least sure: none | <at most three: the place, why, the check that would settle it>
Decisions: none | <each choice the ticket did not dictate: what, over what, why>
Friction: none | <what the brief, docs or tools got wrong or left out, and the fix>
Upstream: none | <a defect in a dependency you worked around: file, lines, the ask>
Screenshots: <paths, light and dark> | n/a: <reason>
```

The `New tests` line is how gate time growth is traced to the lane that added
it.

`Nearby` is what you saw while inside the code and did not do, from what you
already read plus one grep per item: the same defect or untidiness in sibling
places (pattern, number of hits, two examples), a fix that belongs in another
layer, a decision the ticket took silently. Leads, not work: size each as
small (about N lines), a lane, or owner's decision. You were deeper in this
code than the reviewer will be, and the orchestrator cannot ask you later.

`Least sure` is where you made a judgment call or could not verify (an effect
order, a browser you did not run, a path with no test). The reviewer samples a
large diff and may never open that file; the orchestrator runs your check or
points the reviewer there. `Decisions` also go in the commit body: a later
search for "who decided this" must find that an agent did, and why, or the
question returns to the owner. `Friction` is one line per obstacle that cost
you more than a few turns (a wrong command, a rule only a failing gate taught
you, a flaky check); a gotcha about the code itself goes into the project's
own doc in your lane, not here.

Then the project's own labels, if the orchestrator gave any, one per line.

Questions anywhere else in the report get lost. Link logs instead of pasting
them.
