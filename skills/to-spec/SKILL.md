---
name: to-spec
description: Use after a plan is agreed, to write it up as a spec and slice it into tickets agents can build from.
---

# To spec

Synthesis, not an interview. Everything needed is in the conversation, the code
and the tracker; ask only about a gap that changes the result.

## The spec

Read the glossary and ADRs (`docs/agents/domain.md`) and use their words.

- **Problem** and **solution**, from the user's side.
- **Behavior**: numbered list of user/caller capabilities, including edge cases and failures.
- **Decisions**: modules and interfaces ([architecture](../architecture/SKILL.md#vocabulary)),
  schema/contract changes, rejected alternatives worth remembering. No file
  paths or line numbers (they go stale); keep a prototype snippet where it
  beats prose (a reducer, a type).
- **Seams**: where tests observe behavior — as few and high as possible, existing ones first.
- **Out of scope**, explicitly.

## Tickets

Slice into tracer bullets: each cuts a narrow path through every layer, is
independently verifiable, and fits one fresh agent session. Prefactoring first;
set blockers so unblocked tickets can start now. Wide mechanical changes
(codebase renames) are the exception: expand (new beside old), migrate in
batches, contract (delete old) once unused.

Confirm the breakdown (title, blocked by, deliverable) with the user before
publishing via `docs/agents/issue-tracker.md`, blockers first, with native
blocking links.

## Each ticket is a contract

A goal lets the implementer pick an implementation with risks you saw and it did
not. Write the contract instead:

- operation order where order matters;
- invariants as rules ("a mutation that happened is never reported as an error"),
  not lists of places;
- expected result for every outcome, failures included;
- independently checkable acceptance criteria;
- interfaces and behavior, not steps in files.

When review findings cluster in one mechanism, revise the contract or design
instead of patching the third instance. Keep the spec in sync mid-build.
