---
name: cross-review
description: Use when asked for a review, or before shipping a large change. A model of another family reviews blind, as deeply as the change's risk calls for, then one round of fixes.
---

# Cross-review

## Set up

1. **Fixed point.** Resolve base SHA/branch/tag; confirm `git diff <base>...HEAD`
   is non-empty.
2. **Spec.** The issue, spec, or brief answered. None: skip spec pass, say so.
3. **Standards.** Repo coding standards, `docs/agents/checks.md` Review section,
   and three baselines (documented rules override):
   - **Smells:** unclear names, duplication, feature envy, data clumps,
     primitive obsession, repeated switches, shotgun surgery, speculative
     generality, middle men.
   - **Design:** fits existing structure vs bolting on beside it; duplicates
     existing repo behavior (cite existing code).
   - **Tests:** tautologies (constant asserts, recomputing code), testing
     mocks/fakes over real behavior, wrong layer, fixed sleeps or wall-clock
     asserts outside perf suites, duplicate rule tests.
4. **Reviewer.** Use the Review model in `docs/agents/checks.md`, else run
   `<this skill's directory>/scripts/role review --implementer-family <family>`
   (or `--pair` for two-family panels; never read `models.toml` by eye; only
   `role` checks live quotas). Launch per
   [orchestrate Launch](../orchestrate/SKILL.md#launch) and include its
   note/caution in the report.
5. **Depth.** Choose at lane start, tell the lane tool, and state depth + why in
   the report (`docs/agents/checks.md` overrides):
   - **None (exempt):** mechanical docs/renames/generated files; owner-decided
     look with a guard (cite owner quote/date or guard); non-shipped tooling;
     tiny CI/config tweaks. Audit 1 in 5 exempt lanes post-hoc (non-blocking).
   - **Spec only:** ordinary change.
   - **Both passes:** core behavior change or "behavior identical" refactor.
   - **Both passes, two families in parallel:** risky surfaces (migrations,
     auth, money, deletion, process signals, releasing shared holds).
6. **Unit.** One contract per review: one subsystem, <= ~20 files or 1,500
   changed lines. Split larger diffs by subsystem into parallel reviews (each
   gets full file list and shared seams). Batch small unreviewed lanes of one
   subsystem into one diff. When doc/changelog claims need mechanical
   verification, the **coordinator** spawns a flat sibling `scout` pass beside
   the reviewer. A second reviewer must be another family, not a repeat run.

## Review blind

Pass only the diff command, spec, and standards — never the implementer's report
or self-assessment. Reviewers are read-only, run no gates, and follow **Tier 1
(`0` scouts, `depth <= 1`)**: never spawn child subagents; batch parallel
whole-file reads of changed files and immediate callers first-hand. Run required
passes in separate contexts, never merged or reranked:

- **Standards:** each violation with its rule, separating hard violations from
  judgment calls; skip what tooling already enforces.
- **Spec:** missing, partial, unasked, or wrong behavior, quoting the spec line.

Include [references/reviewer-brief.md](references/reviewer-brief.md) in every
brief. With both passes, only the spec pass writes leads and the triage table.
Every review pass (headless or T3 `delegate_task`) must end with the brief's
canonical fenced `json` findings trailer; save the review output to a file and
record it via `lanefather review <id> --record <file> --reviewer <alias>`.

## One round of fixes

Triage findings as soon as review finishes while the diff is fresh; the lane
tool's gate enforces this before further lands. Mark every finding before
promotion or release: `fixed: <commit>` or `rejected: <reason>` (wrong premise,
out of scope, or falsifier passes).

Pre-land reviews (`orchestrate` step 5) fix in the same lane and land once.
Already-landed lanes take one fix round via `lanefather review <id> --fix-lane`
or `start <fix-id> --fix-of A,B,C`, never plain `start` (which loops reviews).
No second review of fixes: on a stray fix-round review, mark findings
`rejected: fix round, not reviewed again (one review per lane)`. Only if the
coordinator verifies a `P0` finding ([reviewer brief](references/reviewer-brief.md))
by running its falsifier and seeing it fail, fix it via the fix-round path
(`--fix-lane` / `--fix-of`), and that fix lands with no further review.

Start each fix by running the finding's falsifier as a failing test; if it
passes, reject with that test. Leads are not findings: route `Follow-ups` per
[orchestrate Finish](../orchestrate/SKILL.md#finish) and filter unresolved
choices through [Owner's decisions](#owners-decisions).

## Owner's decisions

Before escalating a finding, lead, or question, search in authority order (use a
`scout` if wider than a few greps):

1. Project docs, `AGENTS.md`, glossary, and ADRs (`docs/agents/domain.md`).
2. Tracker, PR threads, `git log`, and `git blame` (owner commit = decision;
   agent commit = not).
3. `$XDG_STATE_HOME/mastack/owner-turns.jsonl` (maintained by the friction
   scanner), checking matching repo/feature context and freshness: a chat quote
   is fresh only if newer than the latest commit touching that path or contract
   (`git log -1 -- <path>`) and not superseded by docs or ADRs.

Then:
- **Authoritative or fresh owner decision** (doc/ADR, owner commit, or fresh
  in-context quote): apply and report in one line with citation/quote and date;
  ask only if it breaks something unseen.
- **Older or tangential chat-only remark:** propose as a default with quote and
  date, never silent binding law.
- **Agent decided or nothing found:** settle cheap, reversible in-scope defaults
  yourself (`Decisions`, one-line report). Escalate ONLY irreversible,
  auth-gated, or expensive product/contract trade-offs with options, impact,
  recommendation, and search result.

History never authorizes a push, release, publish, deletion, or spending.

## Report

Depth and why, each pass verbatim, disposition list, one summary line per pass
(count and worst severity), leads with outcomes, and owner decisions found in
history with quotes.
