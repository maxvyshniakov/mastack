---
name: babysit-pr
description: Use when asked to babysit, watch or finish a pull request, or to address its review comments or failing checks. Verifies each finding, fixes with a test, answers every thread.
---

# Babysit PR

One pull request, until nothing on it waits for you: every failing check fixed
or explained, every review thread answered, the rest named as waiting on people.

## Read the repository's rules

The base repository decides the title format, the description template, which
labels and CI triggers exist and who sets them, and whether AI help must be
disclosed. Read its CONTRIBUTING, PR template and agent guidelines, and use its
own PR skills (`.agents/skills`, `.claude/skills`) where it has them. For your
own repositories `docs/agents/publishing.md` is the contract.

A label or CI trigger that maintainers own (`ci:*`, `qa:*`, release labels) is
theirs: report it as waiting, do not add or ask for it in a comment.

## Watch

- When the host can watch the PR and wake you (a PR monitor bound to the
  session), turn it on and let it wake you. It usually needs push access to the
  base repository.
- Otherwise check once per turn. For a longer watch offer a recurring check
  (`/loop`, a schedule) every 30–60 minutes; a review bot answers 5–10 minutes
  after a push, and humans in hours.

## Collect

One table of what needs action, from [queries.md](queries.md):

- each failing check with the failing step, and each pending one;
- each unresolved review thread with author, file and line (only GraphQL says
  whether a thread is resolved);
- each PR-level comment that asks for something and has no answer;
- the newest version of a review bot's summary;
- metadata checks (title, labels, required description sections).

Done when every failing check and unresolved thread is a row.

## Work each row

- **Verify before acting.** Reproduce the claim in the code. Review bots are
  often right about behaviour your change altered and often wrong about intent.
- **A real bug:** write a test that fails, fix, then run the new test against
  the base branch's code too. A behaviour test must pass there, which proves
  you restored the old behaviour rather than invented one; a regression or
  performance test must fail there.
- **Not a bug, or out of scope:** no change; the reply gives the reason.
- **An optional suggestion:** take it when it simplifies; say why if not.
- **A failing check:** read the log and name the step. Rerun only an
  infrastructure failure. Never relax or skip a check to get green.
- **Publish** with the `push` skill or the repository's rules: a new commit per
  round. Rewrite history on a PR under review only when the base forces a
  rebase; review threads anchor to commits.

## Answer

- One reply in every thread you worked: what changed, the commit, the test that
  covers it, or why nothing changed. A request to babysit the PR covers these
  replies. A new issue, an @-mention, a label, closing or re-requesting review
  needs the user's yes.
- A human reviewer's question or objection: draft the reply and give it to the
  user unless they said to answer for them. Many projects close or hide
  AI-only conversations.
- Leave resolving threads to the reviewer unless the repository says authors
  resolve.
- Update the PR description when the change set moved: tests, numbers, scope.

## Report

PR link and head SHA; checks passed, failed and pending, and whom each pending
one waits on; threads fixed, answered and still open; what waits on people
(labels, CI triggers, human review); what you could not verify.
