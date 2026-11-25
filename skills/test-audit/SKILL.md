---
name: test-audit
description: Use monthly, when gate time or flaky failures rise, or when asked to audit a test suite. Read-only; finds tests that cost time or confidence and the change for each.
---

# Test audit

A retro on a test suite. The question: which tests cost the most time or
confidence for what they prove, and what change fixes each class. Read-only:
run no suites and change nothing, so the audit takes no machine slots and leaves
worktrees untouched; the fixes become tickets.

## Where to look

1. **Run history first.** Per suite, from slot/lane stats named in
   `docs/agents/checks.md`, else CI history: runs, p50 and p90, failure and
   retry share. Rank by `runs × time`; a fix pays back in proportion to run
   frequency. Name each number's source.
2. **Size table.** Per suite: tests, test lines, code lines, and fixed per-test
   cost (browser page, subprocess, fresh repo, compiled binary). Where lines go
   matters, not ratio alone.

## Classes

Count each class with a search before reading the heaviest files; cite
`file:line` for every finding (layer and cost rules live in
[tdd](../tdd/SKILL.md#cost-of-a-test)).

- **Unchecked fake.** A double encoding rules under many tests, checked only by
  its own tests. Count its methods against those covered by a shared contract test.
- **Wrong layer.** Browser tests asserting text or model state; DOM-emulator
  tests asserting class names or CSS source text (which pass when the cascade is
  wrong). Cite the cheaper pattern the repo already uses.
- **Wall time as input.** Literal sleeps and settle waits (sum them), sleeps
  before "nothing happened" asserts, `elapsed < N` outside a perf suite. Note
  whether the code accepts an injected clock.
- **Setup per test.** Fresh repo, process or build per test where a shared
  fixture or in-process call suffices (`p50 / test count` gives per-test cost).
- **Mock-call tests of internals.** Call assertions on the project's own
  modules; one rule tested through many entry points or files.
- **Tests that outlived their purpose.** Finished migrations and conversions,
  "removed shape is rejected" tombstones, near-copy files (compare with digits
  normalised).
- **Tautologies and brittle counts.** Asserts on constants, expected values
  recomputed like the code under test, `len(goldens) == N`, bulk-updated snapshots.
- **Churn.** Test files edited in many recent commits — check commit kinds first
  (features = real behavior, refactors = coupling to internals).
- **Gaps hidden by volume.** Large modules with no test beside them. Propose a
  coverage run as a ticket; its result is where to look, not a finding.
- **Unexercised capability branches.** Platform or optional-feature branches
  skipped because the test environment lacks the capability and hits only the fallback.
- **Duplicated scaffolding.** Multi-line mocks or harnesses copy-pasted across
  files with drift instead of one contract-checked test adapter.
- **Silent or swallowed assertions.** Smoke-only checks, error spies hiding real
  warnings, or assertions inside `if` guards or unawaited callbacks.
- **Order-dependent global leaks.** Mutations to globals, env, files, singletons,
  or fake timers without symmetric cleanup (propose shuffled-order runs). For
  web UI examples, see [references/web-ui.md](references/web-ui.md).

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
