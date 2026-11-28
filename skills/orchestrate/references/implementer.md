# Implementer brief

You build one ticket, or the given chain in order, on your own lane branch. The
spec and tickets are the contract; read them with their comments first.

Your lane is registered before you start, and the brief fills your lane id into
its commands (worktree, check, hand-back). Run them as given and open `--help`
only after a command fails: every help or status call rereads your whole context.

## Setup

1. Work only in your worktree, on your lane branch, based on the branch the
   orchestrator named (confirm with `git log -1`). The main checkout,
   integration worktree, and other lanes belong to others.
2. Your claims are the paths you expect to touch. Edit outside them only when
   the ticket needs it, and list each such file under `Outside claims`.
3. Claim each ticket on the tracker when you start it.

## Build

- Use `tdd`. Interfaces and test design are yours.
- Unsettled product question: implement the ticket's default (or today's
  behavior for anything owner-visible) and report it under `Questions`.
- Unasked refactor (`tdd`, "Where the code goes"): do the small one inside your
  claims; put a larger one under `Questions` or `Garden`.
- Keep the diff to your tickets; other lanes edit nearby files on parallel
  branches.
- Batch parallel whole-file reads (up to the ~800-line tool cap) or complete
  structural blocks instead of sequential narrow `Read` line slices or shell
  `sed`/`head`/`tail`/`cat` file slicing (every extra turn resends the whole
  context).
- Keep command output small (every tool result stays in context on later turns):
  wrap noisy commands (>8K output) with `<orchestrate skill dir>/scripts/quiet-cap -- <cmd>`,
  cap searches (`grep -m`, `| head`), run `git show --stat` / `git diff --stat`
  before a full diff, and tail or grep logs instead of printing them whole.
- Respect warm-context ceilings (`reset_context_tokens`: `150K` Anthropic,
  `185K` Google; `max_turns_before_handoff`: `80`): if your session approaches
  either ceiling before finishing, commit clean WIP on your lane branch and
  hand back so the orchestrator can continue in a fresh session.
- Use the brief's focused checks for your edit-check loop, never the full lane
  check; run heavy focused checks through the project's slot wrapper. Multi-minute
  checks run in the background — wait for the completion notice, never in an
  `until grep ...; sleep` loop.

## Before reporting

1. Merge the integration branch tip into your lane once.
2. Commit in the repository's style, with the reason in the body. Leave the
   worktree clean.
3. Run the repo's fast test-hygiene check (`bun run check:hygiene` or
   `package-kit test-hygiene`, when present) before committing new or edited
   tests; follow `tdd` (`## Tests worth keeping`).
4. Follow the brief's `Check:` owner. `Check: mine`: the orchestrator runs the
   lane check beside review after hand-back, so stop at green focused checks
   (Antigravity implementers always use `Check: mine` and must run focused
   checks synchronously before ending their turn, because ending a turn
   terminates child background shell commands). `Check: yours`: run the brief's
   check command once on the committed tree; on red, fix and verify with focused
   checks first, `--rerun` only after they pass, and investigate timeouts alone
   before blaming load.
5. Stop servers and background processes you started, including every loop
   waiting on a stopped command. Report only once `ps` shows nothing of yours
   running in your worktree or scratch (one lane left 53 wait loops on a stopped
   command, holding its worktree and adding load for hours).

## Hand back

Once your part of the checks is green on your last commit, return the report
below and stop. The lane check (when `Check: mine`), review, landing, and
cleanup are the orchestrator's steps; your report is the completion notice. Wait
for none of them and never poll `lanefather list`. If a step genuinely needs a
lane state, `lanefather wait <id> --for <state>` blocks until it; without that
command, put the need under `Questions` and hand back.

## Review fixes

Review runs on your committed tree before land, beside the lane check. Findings
and check failures come back once while your context is warm. Run each finding's
falsifier first as a failing test; if it passes on your tree, reject the finding
with that test as the reason. Fix what holds at its root cause — not with the
reviewer's patch — one finding or root per commit. Merge the integration tip,
run focused checks (and the lane check if `Check: yours`), and hand back. There
is no second review.

## Report

Comment on each ticket: what changed, RED and GREEN evidence, check totals, new
tests with layer and run time, deviations and why. Leave the ticket open (the
orchestrator handles integration labels and default-branch closing). Put known
follow-ups on the ticket as checklist items or linked issues. A lane registered
without a ticket gets none of this; note it under `Questions`.

Return at most 4000 characters to the orchestrator, ending with the footer below
(`<orchestrate skill dir>/scripts/lane-receipt --base <integration branch> --claims <globs>`
prints the mechanical git fields). Emit all 6 mandatory lines (plus `Screenshots` whenever
the lane touches rendering/styles); **omit any other optional field with nothing
to report — never emit `: none` or `n/a` filler for omitted optional fields**:

```text
Branch: <lane branch>
SHA: <final commit>
Worktree: <absolute path>
Checks: <command and totals, or link to the receipt>
Outside claims: none | <paths>
New tests: none | <file>: <count>, <layer (model|render|browser|process)>, <seconds>
```

Optional fields (omit completely when empty):

- `Least sure:` at most 3 (`file:line`, why, check that settles it) — judgment
  calls or unverified paths (effect order, untested browser/path) for the
  reviewer or orchestrator to inspect.
- `Decisions:` choices the ticket left open, prefixed `[owner-visible]` when
  user-facing (`what, over what, why`). Also put in the commit body so later
  searches find an agent's reason instead of re-asking the owner.
- `Questions:` numbered unresolved product/contract choices, each with the
  implemented default. Questions anywhere else in the report get lost.
- `Garden:` 0–3 warm-context leads outside ticket scope (files already read plus
  at most one grep per item: repeating class, untidied sibling symmetry,
  wrong-layer patch, silent contract, or maintainability smell; never fix in
  this lane or invent style nits). Format each in four lines:
  - `[<small|lane>, <high|med>] <file:line> — <what hurts / smells>`
    `Proof:` concrete observation (grep count, broken invariant, live probe)
    `Direction:` owning seam/module + trap to avoid
    `Verify:` test, lint rule, or command that proves the fix
- `Friction:` one line per brief, doc, or tool defect costing turns, and the fix
  (code gotchas belong in project docs inside your lane).
- `Upstream:` dependency defect worked around (`file:line`, upstream ask).
- `Screenshots:` `<light and dark paths> | n/a: <reason>` — **required** on any
  lane touching UI, layout, or styles (omit on non-UI lanes so missing pictures
  are never silent).

`New tests` traces gate time growth to the lane that added it. Append any
project-specific report labels the orchestrator gave, one per line. Link logs
instead of pasting them.
