---
name: babysit-pr
description: Use when asked to babysit, watch or finish a pull request, or to address its review comments or failing checks. Verifies each finding, fixes with a test, answers every thread.
---

# Babysit PR

One pull request, until nothing on it waits for you: every failing check fixed
or explained, every review thread answered, the rest named as waiting on people.

## Read the repository's rules

The base repository decides title format, description template, labels, CI
triggers and who sets them, and AI-disclosure rules. Read its CONTRIBUTING, PR
template, agent guidelines, and repo-local PR skills (`.agents/skills`,
`.claude/skills`). For your own repos `docs/agents/publishing.md` is the contract.

Maintainer-owned labels and CI triggers (`ci:*`, `qa:*`, release labels) are
theirs: report them as waiting; do not add or ask for them in a comment.

## Watch

- If the host provides a session-bound PR monitor (usually needing push access
  to the base repo), turn it on and let it wake you.
- Otherwise check once per turn, or offer a recurring check (`/loop`, schedule)
  every 30–60 minutes; review bots answer in 5–10 minutes, humans in hours.

## Collect

One table of what needs action, from [references/queries.md](references/queries.md):

- each failing check with its failing step, and each pending check;
- each unresolved review thread with author, file and line (GraphQL only);
- each unanswered PR-level comment asking for action;
- the newest review bot summary;
- metadata checks (title, labels, required description sections).

Done when every failing check and unresolved thread is a row.

## Work each row

- **Verify before acting.** Reproduce the claim in code. Review bots are often
  right about altered behaviour and often wrong about intent.
- **A real bug:** reproduce with a failing test ([tdd](../tdd/SKILL.md)), then
  fix. When the finding claims your PR altered existing behavior and the test
  applies cleanly on the base branch (no schema, symbol, or dependency drift),
  run it against base too to confirm it passed before your change.
- **Not a bug, or out of scope:** no change; give the reason in the reply.
- **An optional suggestion:** take it when it simplifies; say why if not.
- **A failing check:** read the log, name the step, and triage per
  [push](../push/SKILL.md#ci) (rerun only infra failures; never relax/skip checks).
- **Publish** via [push](../push/SKILL.md) or repo rules: one new commit per
  round. Rewrite history only when the base forces a rebase; threads anchor to
  commits.

## Answer

- Reply once in every worked thread: what changed, commit, covering test, or why
  nothing changed. A babysit request covers these replies; new issues, @-mentions,
  labels, closing, or re-requesting review need the user's yes.
- Draft replies to human reviewers' questions/objections for the user unless told
  to answer directly (many projects hide AI-only threads).
- Leave resolving threads to the reviewer unless the repo says authors resolve.
- Update the PR description when scope, tests, or numbers moved.

## Report

PR link and head SHA; passed, failed and pending checks (and whom each waits on);
threads fixed, answered and still open; items waiting on people (labels, CI
triggers, human review); what you could not verify.
