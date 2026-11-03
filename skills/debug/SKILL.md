---
name: debug
description: Diagnose a bug or regression from a command that reliably reproduces the exact symptom, through falsifiable hypotheses, to a fix with a regression test and a guard for the whole class of defect. Use for "debug", "почини баг", "почему падает", "тормозит", failing or flaky tests, and audit findings to verify.
---

# Debug

## 1. A loop that goes red

No theory before a reproduction. Build one command that drives the real code
path and asserts the user's symptom: a failing test at some seam, a script
against a running server, a CLI run diffed against known-good output, a browser
script, a replayed capture, a bisect harness. Make it fast and deterministic:
pin time, seed randomness, isolate the filesystem.

Run it and show it red. It must fail on this symptom, not on a neighbor.
Flaky bug: raise the reproduction rate (loops, parallel runs, stress) until it
is debuggable. Physical devices or UI that no command can observe: a repeatable
capture or recorded procedure is the signal; state its limits.

Cannot reproduce: say what you tried, keep investigating read-only, and ask for
access or an artifact. An audit finding you could not reproduce is reported as
"not reproduced", never fixed on speculation.

Then shrink it: cut inputs and steps one at a time until each remaining part is
needed to stay red.

## 2. Hypotheses

Write competing hypotheses, three to five for a hard bug, each with a prediction:
"if X, then changing Y makes it vanish". One that predicts nothing is a guess.
Show the ranked list; the user may rule some out at once. Probe one variable per
step; tag temporary logs with a unique prefix so one grep removes them. For a
performance bug, measure a baseline before changing anything.

## 3. Fix

Write the regression test before the fix, at a seam where the real bug pattern
happens. If no such seam exists, that is an architecture finding: record it
(see `architecture`) instead of writing a test that cannot fail.

Name the class of defect, not just this instance. Search for its siblings in
other paths and fix the class, with a check or test that turns the next instance
red.

## 4. Close

The original loop is green, the regression test passes, tagged logs and
throwaway harnesses are gone, and the commit message states the hypothesis
that proved true. Redact secrets in everything you show.
