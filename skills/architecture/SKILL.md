---
name: architecture
description: Use when looking for badly structured code, designing a module's interface, or when a bug has no clean seam to test at.
---

# Architecture

Goal: a lot of behavior behind a small interface, at a seam where tests and
callers cross the same surface.

## Vocabulary

Use these words exactly; do not drift into component, service, API or boundary.

- **Module**: anything with an interface and an implementation, at any scale.
- **Interface**: everything a caller must know: types, invariants, ordering,
  errors, configuration, performance.
- **Depth**: behavior a caller gets per unit of interface learned. Deep = small
  interface, much behavior. Shallow = interface about as complex as the body.
- **Seam**: the place where behavior can change without editing there; where an
  interface lives.
- **Adapter**: what fills a seam. One adapter is a hypothetical seam; two (say,
  production and test) make it real.
- **Leverage** for callers, **locality** for maintainers: change, bugs and
  knowledge in one place.

## Survey

1. Scope first. Take the user's direction; else find hot spots in
   `git log --name-only` over a long stretch. Recently changed code pays back
   deepening soonest.
2. Read the glossary and ADRs (`docs/agents/domain.md`). Do not re-propose what
   an ADR rejected unless the friction is real enough to reopen it, and say so.
3. Walk the code, with a subagent for breadth, and note friction: one concept
   spread over many small modules, pass-throughs, logic extracted for tests while
   bugs hide in the callers, seams that leak.
4. **Deletion test**: imagine deleting the module. Complexity vanishing means a
   pass-through; complexity reappearing across callers means it earns its keep.
5. **Implicit state machines.** A lifecycle encoded as booleans or optionals
   with unstated valid combinations (`loading`, `ready`, `error?`), status
   strings set from many places, guards like `if state == X and flag` scattered
   across files, phases driven by timers, retries or file presence, or one
   lifecycle mirrored in two places (two languages, a store and its view, a
   file and its reader) with different rules. Write down the states and
   transitions as the code actually behaves, then look for:
   - impossible combinations it can reach;
   - one transition done in two places;
   - stale events overwriting newer state, e.g. a late completion or a replay
     after a rise in rights;
   - transitions with no test.

   The usual fix is one enum carrying data per state, plus one transition
   function or a table-driven reducer, with the transitions tested as a table.
   Not every flag is a machine: a single field with one writer is fine.

Present candidates: files, problem, proposed change, benefit in locality,
leverage and tests, strength (strong, worth exploring, speculative). Do not
propose interfaces yet. Ask which one to explore. Findings are hypotheses;
whether to refactor is the owner's decision.

## Design it twice

For the chosen candidate, classify its dependencies: in-process, local
stand-in available, owned remote (port plus adapters), true external (injected,
mocked in tests). Then have two or three subagents each design a radically
different interface: minimal entry points; most common caller trivial; ports and
adapters. Compare on depth, locality and seam placement, and recommend one,
hybrid if it is better. Tests move to the new interface; delete the old
shallow tests they replace. A rejected candidate with a lasting reason becomes
an ADR, so the next survey does not suggest it again.
