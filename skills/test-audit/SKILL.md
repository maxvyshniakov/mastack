---
name: test-audit
description: Use monthly, when gate time or flaky failures rise, or when asked to audit a test suite. Read-only; finds tests that cost time or confidence and the change for each.
---

# Test audit

A retro on a test suite. The question: which tests cost the most time or
confidence for what they prove, and what change fixes each class. Read-only:
run no suites and change nothing, so the audit can run beside other agents;
the fixes become tickets.

## Where to look

1. **Run history first.** Per suite, from the stats of the slot and lane tools
   that `docs/agents/checks.md` names, else CI history: runs, p50 and p90,
   failure and retry share. Rank by runs × time; a fix pays
   back in proportion to how often the suite runs. Name the source of each
   number.
2. **Size table.** Per suite: tests, test lines, code lines, and the fixed cost
   of one test (a browser page, a subprocess, a fresh repository, a compiled
   binary). A ratio alone is not a finding; where the lines go is.

## Classes

Count each class with a search before reading files, then read the heaviest
files. Every finding cites `file:line`.

- **Unchecked fake.** A double that encodes rules, under many
  tests, checked only by its own tests. Count the methods it implements
  against those a contract test runs on both it and the real implementation.
- **Wrong layer.** Browser tests whose assertions are text or model state;
  DOM-emulator tests that assert class names or CSS source text, which pass
  when the cascade is wrong. Find the cheaper pattern the repository already
  uses and cite it.
- **Wall time as input.** Literal sleeps and settle waits (sum them), a sleep
  before a "nothing happened" assert, `elapsed < N` outside a perf suite.
  Note whether the code takes an injected clock; without one the tests cannot
  stop sleeping.
- **Setup per test.** A fresh repository, process or build per test where a
  class fixture or an in-process call would do. Measured p50 divided by the
  test count gives the cost per test.
- **Mock-call tests of internals.** Call assertions on the project's own
  modules; one rule tested through many entry points or files.
- **Tests that outlived their purpose.** Finished migrations and conversions,
  "removed shape is rejected" tombstones, near-copy files (compare them with
  digits normalised).
- **Tautologies and brittle counts.** An assert on a constant, an expected
  value recomputed the way the code does, `len(goldens) == N`, snapshots
  updated in bulk.
- **Churn.** Test files edited in many recent commits. Read the commit kinds
  first: features mean real behavior, refactors mean coupling to internals.
- **Gaps hidden by volume.** Large modules with no test beside them. Propose a
  coverage run as a ticket; its result is where to look, not a finding.

Also list what is already done well, so a fix does not remove it.

## Report

- Per finding: an ID, the evidence with counts and `file:line`, the change,
  the gain (time, flakes, confidence or churn) marked measured or estimated,
  and the priority.
- A ranked summary table, then the patterns shared across suites.
- Mechanical checks to propose, each as a ratchet: today's count may only go
  down, and a deliberate exception carries a marked reason on the line. A new
  warning nobody must fix stops being read.

Each finding is a hypothesis until its ticket reproduces it; owner rules or
data (deleting a conversion, a perf budget) go to the owner as questions.
