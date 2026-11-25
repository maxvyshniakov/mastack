# Reviewer brief

Asked on top of each review pass. The reviewer already paid to read the diff,
surrounding code, and engine; these questions cost output only (10–20%) and
avoid forcing the orchestrator to reread the same code.

Finish Part 1 before starting Part 2 (mixing them dilutes the defect hunt).
Read source files with `Read` (line ranges) rather than `cat`/`sed` in bash,
and scope `git diff` per file to avoid `large-bash-output` friction entries.

## Part 1: each finding

A stable id (`F1`, `F2`, …), severity (`P0`: data loss, security/auth breach,
crash, or broken public contract; `P1`: behavior bug or missing requirement;
`P2`: minor defect, edge-case gap, or maintainability issue), file and line,
what is wrong, a concrete scenario (inputs → wrong result), how it was verified,
and:

- **Confidence and falsifier.** High, medium or low; the cheapest check that
  confirms or kills the finding (one-sentence unit test or browser
  measurement); and any unseen assumption (effect order, engine or browser
  behaviour — a finding hinging on effect order once arrived as a flat P1 and
  cost a second read to discover).
- **Should have been caught by.** The existing test that ought to fail and why
  it does not, else the cheapest new guard (unit test, browser check, lint rule
  or source-scan test).
- **Fix direction.** The layer to fix in and the layer not to, size ("about N
  lines" or "a lane"), and consumer visibility. No fix code: reviewers patch
  symptoms where seen and implementers anchor on the patch.
- **Parameterized browser checks.** For every loop over states (`for (const
  side of ...)` / `args=...`), verify the script asserts the requested state
  took effect in the DOM (`data-side`, `dir`, `data-variant`, etc.) rather than
  trusting URL `args=` (which Storybook can silently drop).

Then what was examined and found sound, and what was not examined.

## Part 2: wider than the diff

At most five items, ids `W1`…; "nothing" is a full answer. From what you
already read plus at most one repository-wide grep per item. Mark each item
unverified unless verified, and split into two buckets:

- **Follow-ups** (`small` — about N lines, one sensible outcome — or `lane`):
  0–3 high-leverage systemic/cross-cutting leads to fix or queue without asking
  the owner (`none` is a complete answer — never invent filler). Kinds:
  **class** (repeating pattern with grep hit count, 2–3 examples, and closing
  guard), **symmetry** (tidied in one place, untidied beside it), **wrong
  level** (patch in wrong layer or tooling workaround in prod), or **unasked**
  (silent contract or consumer-visible change). Format each in four lines so
  the next agent starts warm:
  - `[<small|lane>, <high|med>] <file:line> — <what hurts / smells>`
  - `Proof:` concrete observation (grep hit count, broken invariant, live probe)
  - `Direction:` owning seam/module plus trap to avoid
  - `Verify:` test, lint rule, or command that proves the fix
- **Owner decisions** (omit if empty): ONLY choices meeting
  [Owner's decisions](../SKILL.md#owners-decisions) (irreversible, auth-gated,
  or expensive product/contract trade-offs not answered by docs or ticket —
  never engineering defaults or obvious follow-ups). Write each as the question
  itself: one sentence of context, 2–3 options with what each changes or
  breaks, and the recommended option with reason.

## Part 3: triage

- **Roots.** Ids sharing one cause, with the cause in a line.
- **Top three.** Ids to fix if only three get fixed, in order.
- **Table.** One row per id: id | severity or "lead" | file | root |
  confidence | falsifier | size | consumer-visible (used to compare and
  deduplicate dual-reviewer reports).

End with counts by severity, the top three, and the share of effort Parts 2 and
3 took.
