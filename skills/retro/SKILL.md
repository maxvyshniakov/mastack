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

- **Mechanical** (a wrong command, a banned pattern, a step skipped, a check not
  run): it gets a hook, lint rule, test or tool change. First look for a check
  that already exists but is not wired in, or is silently broken; wiring it is
  the fix. A repository with no guard at all (no hook, no CI running its checks)
  is itself a finding.
- **Judgment** (the wrong trade-off, a misread spec): a rule for the reviewer,
  in the project's standards. The reviewer has the least context pressure, so
  standards are enforced in review, not loaded on the implementer.
- **Navigation**: the agent searched long for something. Add a pointer where it
  looked first.
- **Information access**: the agent could not see something it needed (a log,
  a service's state). Give it read access.
- **Tool economy**: an expensive call that a cheaper command or a better tool
  output would replace.
- **Instructions**: an instruction that was ignored or misled. Fix it with
  `agent-docs`.

## Prove it bites

A new check counts only when it has been seen to fail on the original mistake
and pass on the fix. Reproduce the mistake against the check before
reporting it as done.

## Report

Findings in order of how likely they are to recur, each with the evidence from
the session, the layer, the change, and whether it is done and proven or
proposed. Propose; change shared configuration or global rules only with the
user's go-ahead.
