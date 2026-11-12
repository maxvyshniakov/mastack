---
name: tdd
description: Use when implementing a feature or fix with checkable behavior, or when asked for TDD. Test-first, one red-green slice at a time.
---

# TDD

## Seams

Test behavior through public interfaces, the way callers use them. Choose the
seams yourself, prefer existing interfaces, and name them before the first test:
"behavior X, observed through Y". Ask the user only about product behavior that
is still undecided, not about seams or test strategy. When the interface itself
is in question, use the vocabulary of `architecture`.

## The loop

One slice per cycle, vertical: one test, the least code that passes it, repeat.
Each test is a tracer that reacts to what the previous cycle taught.

1. **Red.** Write the test. Run it. See it fail for the expected reason, not on
   a typo or setup error.
2. **Green.** Write the minimum to pass. No speculative features.
3. Next slice.

Refactoring is not part of the loop; it belongs to review.

## Tests worth keeping

- Assert observable outcomes through the interface, not internal calls, private
  methods or a side channel such as querying the database directly.
- Expected values come from an independent source: a literal, a worked example,
  the spec. An assertion that recomputes the answer the way the code does passes
  by construction.
- Mock only at the system boundary: external services, time, randomness,
  sometimes the filesystem. Never your own modules.
- No writing all tests first; bulk tests check imagined shapes.

Pure styling and docs need their own checks (visual, link, lint), not TDD. When
no stable automated test can observe the outcome, say so and use focused runtime
or device evidence. A test that greps source text is not a behavior test.

## Cost of a test

Every test runs on every gate for as long as it exists, so its cost counts.

- **Cheapest layer that observes the behavior.** A model or reducer test for
  rules and state; a render without a browser (server render, DOM emulator)
  for markup, text and roles; a real browser only for layout, focus, pointer
  and keyboard events, and paint; a subprocess only for exit codes, signals and
  real I/O, the rest through an in-process call. A browser test pays for a process, a page load
  and a settle wait; a DOM emulator cannot resolve the cascade, so class names
  or CSS text asserted there pass while the paint is wrong.
- **No fixed sleeps.** Fake or inject the clock, or wait for the condition or
  event. To show that something did not happen, wait for the event that would
  have carried it (the next tick, the reply) or assert against the code's own
  delay. A sleep is too slow on an idle machine and too short under load, and a
  sleep before "nothing happened" passes whenever the system is slow.
- **Timing asserts only in the perf suite.** Elsewhere assert the order of
  events or the injected value; a generous deadline that only stops a hang is
  fine. Wall time depends on machine load, not on the code.
- **A snapshot or golden only if someone reads its diff.** One that is updated
  in bulk passes anything. Compare goldens by name, not by count: a count passes
  when one is swapped for another, and every new one edits the test.
- **A fake is checked against the real implementation.** A double that encodes
  rules runs the same contract tests as the real thing; its own tests prove
  nothing, and every test built on it asserts rules nobody checks.

## Checks

During the loop run focused tests only (`docs/agents/checks.md`), with heavy
ones through the project's slot wrapper. Leave the full gate for the end, once,
before the push.

## Report

The seam, the RED failure as observed, the GREEN result, each new test with its
layer and run time, the commands, and any evidence that is missing.
