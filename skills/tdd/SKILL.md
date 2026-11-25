---
name: tdd
description: Use when implementing a feature or fix with checkable behavior, or when asked for TDD. Test-first, one red-green slice at a time.
---

# TDD

## Seams

Test behavior through public interfaces, the way callers use them. Choose seams
yourself, prefer existing interfaces, and name them before the first test:
"behavior X, observed through Y". Ask the user only about undecided product
behavior, not seams or test strategy. When the interface itself is in question,
use the vocabulary of `architecture`.

## Where the code goes

Build the change inside the existing structure, not beside it. Look for code
that already does the behavior (module, package, repo shared code) and use or
extend it. When a clean version needs an unasked refactor, do the small one in
your scope, or build the asked version and propose the refactor in the report;
never add a second copy silently.

## The loop

For new or uncertain interfaces, work vertically one slice at a time: one test,
least code to pass, repeat — bulk up-front tests freeze imagined shapes. When
the interface is already settled (bug fix with edge cases, transition/parser
table), batch related cases or a parameterized table into one RED/GREEN cycle.

1. **Red.** Run the test(s) and confirm failure for the expected reason, not a
   typo or setup error.
2. **Green.** Write the minimum to pass. No speculative features.
3. Next slice. Refactor inside the loop only to fit the change in; propose
   wider refactors in the report.

## Tests worth keeping

- Observe outcomes through the caller's durable contract (return values,
  events, rendered output, or persisted rows/files when durability, schema
  migration, or cross-process state is the contract) — never private methods,
  internal call counts, or private internal tables.
- Derive expected values from an independent source (literal, worked example,
  spec); asserting a recomputation of the code passes by construction.
- Match doubles to [architecture](../architecture/SKILL.md#design-it-twice)
  dependency tiers: real `in-process` modules and real temp directories (mock
  FS only for unproducible OS errors like `ENOSPC`/`EACCES`), a `local
  stand-in` or contract-checked adapter for `owned remote`, and mocks/injection
  only for `true external` boundaries (third-party network, clock, randomness).
- Never weaken or delete a new, edited, or existing assertion to get green or
  satisfy a hygiene checker (such as `calls.length > 0` or asserting CSS class
  names): when the spec genuinely changed the behavior, update the assertion
  and cite the spec line. Never dismiss a failure as "baseline red" without
  proving it fails identically on the base commit (check in a temporary detached
  worktree under `.claude/worktrees/`, never `git stash` or `git checkout` over
  dirty files).

Pure styling and docs use visual, link, or lint checks, not TDD. When no stable
automated test can observe the outcome, say so and use focused runtime or
device evidence. Source-text grep is not a behavior test.

## Cost of a test

Every test runs on every gate for as long as it exists, so its cost counts.

- **Cheapest layer that observes the behavior.** Model/reducer test for rules
  and state; non-browser render (server render, DOM emulator) for markup, text,
  roles; real browser only for layout, focus, pointer/keyboard events, paint;
  subprocess only for exit codes, signals, real I/O (rest in-process). A DOM
  emulator cannot resolve the cascade, so class-name/CSS asserts pass while
  paint is wrong.
- **No fixed sleeps.** Fake or inject the clock, or wait for the condition or
  event. To prove something did not happen, advance an injected/faked clock
  past the spec's threshold or flush the event/queue that would have carried
  it. A sleep is too slow idle, too short under load, and passes "nothing
  happened" whenever the system is slow.
- **Timing asserts only in the perf suite.** Elsewhere assert event order or
  injected values (wall time tracks machine load, not code); a generous hang
  deadline is fine.
- **Snapshot/golden only if someone reads its diff.** Bulk-updated goldens pass
  anything; compare goldens by name, not count (a count passes when one golden
  is swapped for another, and every new one edits the test).
- **Fake checked against the real implementation.** Any double encoding rules
  runs the same contract tests as the real thing (a fake's own tests prove
  nothing, and tests built on it assert unchecked rules).

## Checks

Run focused tests only during the loop (`docs/agents/checks.md`), with heavy
ones through the project's slot wrapper. Leave the full gate for once at the
end, before pushing.

## Report

Seam, observed RED failure, GREEN result, commands, missing evidence, and:
`New tests: none | <file>: <count>, <layer (model|render|browser|process)>, <seconds>`
(inside an `orchestrate` lane, use the implementer brief footer).
