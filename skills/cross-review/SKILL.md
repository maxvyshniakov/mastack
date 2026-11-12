---
name: cross-review
description: Use when asked for a review, or before shipping a large change. A model of another family reviews in two blind passes, then one round of fixes.
---

# Cross-review

## Set up

1. **Fixed point.** The base the work started from: a SHA, branch or tag.
   Resolve it and check the diff `git diff <base>...HEAD` is not empty.
2. **Spec.** The issue, spec or brief the work answers. None: the spec pass is
   skipped and the report says so.
3. **Standards.** Coding standards the repository documents, and the Review
   section of `docs/agents/checks.md`: project rules and what to ignore. On
   top, a smell baseline, always as a judgment call that a documented rule
   overrides: unclear names, duplication, feature envy, data clumps, primitive
   obsession, repeated switches, shotgun surgery, speculative generality,
   middle men. And a test baseline, since nothing else reads the tests and the
   implementer wrote them to pass: a tautology (asserts a constant, recomputes
   the code's answer), a test of a mock or fake instead of the real thing, the
   wrong layer (a browser for text, a DOM emulator for paint), fixed sleeps or
   wall-clock asserts outside a perf suite, a duplicate of an existing test of
   the same rule.
4. **Reviewer.** The model the Review section of `docs/agents/checks.md` names,
   else role `review` in `models.toml`: a model of a different family from the
   implementer, with the fallback it lists. For risky surfaces
   (migrations, auth, money, deletion) run both families in parallel.

## Review blind

The reviewer gets the diff command, the spec and the standards, and nothing
else: not the implementer's report, summary or self-assessment. Reviewers are
read-only; they run no gates.

Two passes, separate contexts, never merged or reranked against each other:

- **Standards**: each violation with the rule it breaks, hard violations apart
  from judgment calls; skip what tooling already enforces.
- **Spec**: what is missing or partial, what was not asked for, what looks
  implemented but wrong. Quote the spec line for each.

## One round of fixes

The implementer answers every finding once:

- `fixed: <commit>`
- `rejected: <reason>`, a concrete reason such as wrong premise, out of scope,
  or contradicted by a test.

No second review of the fixes; review loops do not converge. A finding that
needs a decision from the owner goes to them with a recommendation instead of
being fixed or rejected.

## Report

Both passes as returned, then the disposition list, then one line per pass: the
number of findings and the worst one.
