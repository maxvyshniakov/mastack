---
name: retro
description: Use after something went wrong in a session, or when asked for a retro. Turns mistakes into hooks, checks or reviewer rules.
---

# Retro

The output is changes to what the next agent works in: checks, hooks, docs,
skills, tools. Not a summary of the session.

## Read the primary source

The session itself: its transcript or log, the commands that ran, the diff, the
review findings, the user's corrections. Default to the current session. Note
each place where time was lost or a mistake was made, and what the agent
believed at that moment.

## Classify each finding

- **Mechanical** (wrong command, banned pattern, skipped step, unrun check):
  hook, lint rule, test or tool change. First check for an existing unwired or
  silently broken guard; wiring it is the fix. A repository with no guard at all
  (no hook, no CI running checks) is itself a finding.
- **Judgment** (wrong trade-off, misread spec): a reviewer rule in the project's
  standards (reviewers have the least context pressure, not implementers). When
  the same review finding recurs across tasks in this session, promote it from
  Judgment to Mechanical (lint, hygiene, or test check).
- **Navigation**: the agent searched long for something — add a pointer where it
  looked first.
- **Information access**: the agent lacked visibility (log, service state) —
  grant read access.
- **Tool economy**: an expensive call replaceable by a cheaper command or
  cleaner output.
- **Test** (flake, slow gate, missed bug): run [test-audit](../test-audit/SKILL.md)
  on that suite; turn findings into tickets and land the ratchet that bites (one
  bad test is usually a suite-wide pattern). Test OS-specific checks locally
  against fake inputs so local gates catch what otherwise runs only on another
  OS in CI.
- **Instructions**: ignored or misleading instruction — fix with
  [agent-docs](../agent-docs/SKILL.md).

## Prove it bites

A new check counts only when it has been seen to fail on the original mistake
and pass on the fix. Reproduce the mistake against the check before
reporting it as done.

## Report

Omit accomplishments and "what went well". Every bullet must name a concrete
artifact to change — hook, check, test, reviewer rule, doc, or skill; an
unowned "be more careful next time" is not a finding. List findings in order of
how likely they are to recur, each with the evidence from the session, the
layer, the change, and whether it is done and proven or proposed. Propose;
change shared configuration or global rules only with the user's go-ahead.
