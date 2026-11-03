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
- **Behavior**: a numbered list of what users and callers can do, covering edge
  cases and failures, not only the happy path.
- **Decisions**: modules and their interfaces, schema and contract changes,
  rejected alternatives worth remembering. No file paths or line numbers; they
  go stale. A snippet from a prototype may stay where it states a decision more
  precisely than prose (a reducer, a type).
- **Seams**: where tests will observe the behavior. As few as possible, as high
  as possible, existing ones first.
- **Out of scope**, explicitly.

## Tickets

Slice into tracer bullets: each ticket cuts a narrow path through every layer,
is verifiable on its own, and fits one fresh agent session. Prefactoring comes
first. Give each ticket its blockers; a ticket with none can start now.

A wide mechanical change (a rename across the codebase) is the exception: expand
(new form beside the old), migrate in batches, contract (delete the old form)
once nothing uses it.

Show the breakdown (title, blocked by, what it delivers) and adjust it with the
user before publishing. Publish through `docs/agents/issue-tracker.md`, blockers
first, using the tracker's native blocking links.

## Each ticket is a contract

A goal lets the implementer pick an implementation whose risks you saw and it
did not. Write the contract instead:

- the order of operations where order matters;
- what is forbidden, as a rule ("a mutation that happened is never reported as
  an error"), not as a list of places;
- the expected result in every outcome, failures included;
- acceptance criteria that can each be checked on their own;
- interfaces and behavior, not steps in files.

When review findings keep landing in one mechanism, change the contract or the
design; do not patch the third instance. Keep the spec in sync when a decision
changes mid-build.
