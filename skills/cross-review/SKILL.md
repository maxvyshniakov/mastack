---
name: cross-review
description: Use when asked for a review, or before shipping a large change. A model of another family reviews blind, as deeply as the change's risk calls for, then one round of fixes.
---

# Cross-review

## Set up

1. **Fixed point.** Resolve the base SHA/branch/tag and confirm
   `git diff <base>...HEAD` is non-empty.
2. **Spec.** The issue, spec, or brief the work answers. None: skip the spec
   pass and say so.
3. **Standards.** Repository coding standards plus the Review section of
   `docs/agents/checks.md`, plus three baselines (documented rules override):
   - **Smells:** unclear names, duplication, feature envy, data clumps,
     primitive obsession, repeated switches, shotgun surgery, speculative
     generality, middle men.
   - **Design:** does the change fit existing structure or bolt on beside it;
     does it duplicate existing repository behavior (cite the existing code).
   - **Tests:** tautologies (constant asserts, recomputing code), testing
     mocks/fakes instead of real behavior, wrong layer, fixed sleeps or
     wall-clock asserts outside perf suites, duplicate tests of the same rule.
4. **Reviewer.** Use the model in `docs/agents/checks.md` under Review, else run
   `<this skill's directory>/scripts/role review --implementer-family <family>`
   (never read `models.toml` by eye; only `role` reads live quotas). Use its
   command or `delegate_task` target (`codex exec` needs `-s read-only` and
   `< /dev/null`) and include its note/caution in the report.
5. **Depth.** Choose at lane start and tell the lane tool (state depth and why
   in the report; `docs/agents/checks.md` overrides):
   - **None (exempt):** mechanical docs/renames/generated files; owner-decided
     look with a guard (record owner quote/date or guard name); non-shipped
     tooling; tiny CI/config tweaks. Audit 1 in 5 exempt lanes post-hoc
     (non-blocking).
   - **Spec only:** ordinary change.
   - **Both passes:** core behavior change or "behavior identical" refactor.
   - **Both passes, two families in parallel:** risky surfaces (migrations,
     auth, money, deletion, process signals, releasing shared holds).
6. **Unit.** One contract per review: one subsystem, up to ~20 files or 1,500
   changed lines. Split larger diffs by subsystem into parallel reviews (each
   gets the full file list and shared seams). Batch small unreviewed lanes of
   one subsystem into one diff. Run doc/changelog claims against code as a
   separate `scout` pass. A second reviewer must be another family, not a repeat
   run.

## Review blind

Give the reviewer only the diff command, spec, and standards — never the
implementer's report or self-assessment. Reviewers are read-only and run no
gates. Run required passes in separate contexts, never merged or reranked:

- **Standards:** each violation with its rule, separating hard violations from
  judgment calls; skip what tooling already enforces.
- **Spec:** missing, partial, unasked, or wrong behavior, quoting the spec line.

Include [references/reviewer-brief.md](references/reviewer-brief.md) in every
brief (falsifier, missing guard, fix direction, up to 5 wider leads, triage
table). With both passes, only the spec pass writes leads and the triage table.

## One round of fixes

Triage findings as soon as the review finishes while the diff is fresh; the lane
tool's gate enforces this before further lands. Mark every finding before
promotion or release:

- `fixed: <commit>`
- `rejected: <reason>` (wrong premise, out of scope, or falsifier passes).

Pre-land reviews (`orchestrate` step 5) fix in the same lane and land once.
Already-landed lanes start one fix round via the lane tool's fix-round path
(`lanefather review <id> --fix-lane` or `start <fix-id> --fix-of A,B,C`), never
a plain `start` (which loops reviews). No second review of fixes: if one runs
anyway, mark its findings `rejected: fix round, not reviewed again (one review
per lane)`.

Start each fix by running the finding's falsifier as a failing test; if it
passes, reject with that test. Leads are not findings: fold a small same-root
lead into the fix round, count a wider class with a scout and file a ticket, and
route the rest to [Owner's decisions](#owners-decisions).

## Owner's decisions

Before escalating a finding, lead, or question to the owner, search (using a
scout if wider than a few greps):

- `$XDG_STATE_HOME/mastack/owner-turns.jsonl` (maintained by `bin/friction scan`),
  then raw session histories (`~/.claude/projects`, `~/.codex/sessions`,
  `~/.t3/userdata/providers`) for the symbol/file and owner messages;
- the tracker, `git log`, and `git blame` (an owner commit is a decision; an
  agent commit is not).

Then:
- **Owner decided it** (unreversed quote or commit): apply and report in one
  line with quote and date; ask only if it breaks something unseen.
- **Agent decided it** or nothing found: settle cheap, reversible in-scope
  defaults yourself (report in one line); otherwise ask with options, impact,
  recommendation, and search result.

History never authorizes a push, release, publish, deletion, or spending.

## Report

Depth and why, each pass verbatim, disposition list, one summary line per pass
(count and worst severity), leads with outcomes, and owner decisions found in
history with quotes.
