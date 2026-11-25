---
name: debug
description: Use for bugs, regressions, failing or flaky tests, slowness, and audit findings to verify. Reproduce first; fix with a regression test.
---

# Debug

## 1. A loop that goes red

No theory before a reproduction. Build one fast, deterministic command driving
the real code path and asserting the user's symptom (failing seam test, script
against a server, CLI diff, browser script, replay, or bisect; pin time, seed
randomness, isolate the filesystem).

Run it and show it red on this exact symptom. For flakes, raise the reproduction
rate (loops, parallel runs, stress) until debuggable. For physical devices or
unobservable UI, a repeatable capture or procedure is the signal; state its limits.

Cannot reproduce: say what you tried, investigate read-only, and ask for access
or an artifact. Report unverified audit findings as "not reproduced"; never fix
on speculation.

Shrink the repro by cutting inputs and steps until every remaining part is
required to stay red.

## 2. Hypotheses

Write competing hypotheses (three to five for a hard bug), each with a
prediction: "if X, changing Y makes it vanish" (one that predicts nothing is a
guess). Show the ranked list; the user may rule some out at once. Probe one
variable per step; prefix temporary logs so one grep removes them. For
performance bugs, measure a baseline before changing anything.

## 3. Fix

Write the regression test before the fix ([tdd](../tdd/SKILL.md)), at a seam
where the real bug pattern happens. No such seam is an
[architecture](../architecture/SKILL.md) finding: record it instead of writing a
test that cannot fail.

Name the defect class, not just this instance. Search for siblings in other
paths and fix the class with a check or test that turns the next instance red.

## 4. Close

Original loop green, regression test passing, tagged logs and throwaway
harnesses removed, commit message naming the hypothesis that proved true, and
secrets redacted from all output.
