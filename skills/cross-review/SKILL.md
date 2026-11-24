---
name: cross-review
description: Use when asked for a review, or before shipping a large change. A model of another family reviews blind, as deeply as the change's risk calls for, then one round of fixes.
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
   middle men. Two design questions on top: does the change fit the structure
   it lands in, or is it bolted on beside it (and which refactor would make it
   fit); and does it add a copy of behaviour the repository already has (name
   the existing code). And a test baseline, since nothing else reads the tests and the
   implementer wrote them to pass: a tautology (asserts a constant, recomputes
   the code's answer), a test of a mock or fake instead of the real thing, the
   wrong layer (a browser for text, a DOM emulator for paint), fixed sleeps or
   wall-clock asserts outside a perf suite, a duplicate of an existing test of
   the same rule.
4. **Reviewer.** The model the Review section of `docs/agents/checks.md` names,
   else what `<this skill's directory>/scripts/role review
   --implementer-family <family>` prints: model, effort and command, and its
   note and caution in the report. Use its answer, not your reading of
   `models.toml`: only it reads the live quotas.
5. **Depth.** Match the review to what the change can break; the Review
   section of `docs/agents/checks.md` says which paths fall where, else judge
   by the diff. State the depth you chose and why in the report.
   - Mechanical (docs, a rename or move, regenerated files with no code
     change): no review.
   - Ordinary change: the spec pass only.
   - Behaviour change in the core, or a refactor declared "behaviour
     identical": both passes.
   - Risky surface (migrations, auth, money, deletion, signals to processes,
     releasing what another process holds): both passes, and both families in
     parallel where `role` offers a reviewer of another family.

6. **Unit.** One review covers one contract: one subsystem, up to about 20
   files or 1,500 changed lines. Split a larger diff by subsystem into
   parallel reviews; each gets the whole file list for context, its own files
   to answer for, and by name any seam it shares with another part. A
   reviewer samples a diff that large instead of covering it: five full
   reviews of one 4,700-line merge shared three findings and each found
   others. Small lanes of one subsystem that landed unreviewed are reviewed
   together as one diff: the reading is paid once, and a guard from one lane
   is checked against the writer in another. Claims in docs, changelog and
   comments against the code are a pass of their own for the scout model;
   inside the defect hunt they take its attention. A second reviewer is
   another family, not another run: two families shared fewer findings than
   two runs of one.

## Review blind

The reviewer gets the diff command, the spec and the standards, and nothing
else: not the implementer's report, summary or self-assessment. Reviewers are
read-only; they run no gates.

The passes the depth calls for, in separate contexts, never merged or reranked
against each other:

- **Standards**: each violation with the rule it breaks, hard violations apart
  from judgment calls; skip what tooling already enforces.
- **Spec**: what is missing or partial, what was not asked for, what looks
  implemented but wrong. Quote the spec line for each.

Every reviewer's brief also asks for what
[references/reviewer-brief.md](references/reviewer-brief.md) lists: a
falsifier, the missing guard and a fix direction per finding, up to five leads
wider than the diff, and a triage table. When both passes run, only the spec
pass writes the leads and the table.

## One round of fixes

Triage findings when the review finishes or the lane list/stop hook reports
them, while the diff is fresh; the [Lanefather gate](https://github.com/maxvyshniakov/fathers/issues/177)
enforces this before further lands. Every finding is marked fixed or rejected
before promotion or release. The implementer answers every finding once:

- `fixed: <commit>`
- `rejected: <reason>`, a concrete reason such as wrong premise, out of scope,
  or contradicted by a test.

A lane reviewed before its land (`orchestrate` step 5) gets its findings in
the same lane, from the same implementer, and lands once. For a lane that had
already landed, with a lane tool, the fix round starts through its fix-round path
(Lanefather: `review <id> --fix-lane`, or `start <fix-id> --fix-of A,B,C` for
several lanes' findings), never a plain `start`: the tool reviews an ordinary
lane at land, and fix lanes started that way chained six rounds deep.

No second review of the fixes; review loops do not converge. A review of fix
work that runs anyway opens no new round: each of its findings is marked
`rejected: fix round, not reviewed again (one review per lane)`, so the lane
finishes.

A fix starts from the finding's falsifier as a failing test; a finding whose
falsifier passes is rejected with that test as the reason. Leads are not
findings and are not marked: a small one of the same root joins the fix round,
a class gets its hits counted by a scout and a ticket, the rest go to
[Owner's decisions](#owners-decisions).

## Owner's decisions

Before a finding, lead or lane question goes to the owner, look for the answer
they already gave; most such questions were decided in an earlier session, and
each one asked again costs them a round trip. Search, with a scout when it is
more than a couple of greps:

- the session histories of every harness the owner uses (Claude Code
  `~/.claude/projects`, Codex `~/.codex/sessions`, T3 Code and Antigravity
  under `~/.t3/userdata/providers`), for the file, symbol or token name and
  for the owner's own messages around it;
- the tracker, and `git log` and `git blame` of the lines: a hand-made commit
  by the owner is a decision, an agent's commit is not.

Then:

- **The owner decided it** (their words, or their own commit, and nothing
  later reverses it): apply the decision and report it in one line with the
  quote and its date. If what they chose breaks something they could not have
  seen, ask about that breakage only, with the quote.
- **An agent decided it**, or nothing is found: settle it yourself when
  `orchestrate` step 9 lets you; otherwise ask, with the options, what each
  breaks, your recommendation, and what the search found.

History never authorizes a push, release, publish, deletion or spending:
approval given in one context does not carry to the next.

## Report

The depth and why, each pass as returned, then the disposition list, then one
line per pass: the number of findings and the worst one. Then the leads with
what became of each, and the owner's decisions found in history, each with
its quote.
