# Implementer brief

You build one ticket, or the given chain in order, on your own lane branch. The
spec and tickets are the contract; read them with their comments first.

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
- Keep the diff to your tickets; other lanes edit nearby files right now.
- Focused checks while working; heavy ones through the project's slot wrapper.

## Before reporting

1. Merge the integration branch tip into your lane once.
2. Commit in the repository's style, with the reason in the body. Leave the
   worktree clean.
3. Run the lane's checks on the committed tree. Fix red ones; investigate a
   timeout alone before blaming load.
4. Stop servers and background processes you started.

## Review fixes

You may be resumed once with review findings. Fix each that holds, reject the
others with a reason in the commit and report, check, report. There is no
second review.

## Report

Comment on each ticket: what changed, RED and GREEN evidence, check totals,
deviations and why. Leave the ticket open.

Return at most 4000 characters to the orchestrator, ending with:

```
Branch: <lane branch>
SHA: <final commit>
Worktree: <absolute path>
Checks: <command and totals, or link to the receipt>
Outside claims: none | <paths>
Owner-visible defaults changed: none | <each one>
Questions: none | <numbered, each with the default you implemented>
Screenshots: <paths, light and dark> | n/a: <reason>
```

Questions anywhere else in the report get lost. Link logs instead of pasting
them.
