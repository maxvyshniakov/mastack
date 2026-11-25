---
name: architecture
description: Use when looking for badly structured code, designing a module's interface, or when a bug has no clean seam to test at.
---

# Architecture

Goal: a lot of behavior behind a small interface, at a seam where tests and
callers cross the same surface.

## Vocabulary

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
   strings set from many places, scattered `if state == X and flag` guards,
   phases driven by timers, retries or file presence, or one lifecycle mirrored
   in two places (two languages, store and view, file and reader) with different
   rules. Write down the states and transitions as the code behaves, then look for:
   - impossible combinations it can reach;
   - one transition done in two places;
   - stale events overwriting newer state (late completion, replay after privilege rise);
   - transitions with no test.

   Fix with one enum carrying data per state plus one transition function or
   table-driven reducer, tested as a table. Not every flag is a machine: a
   single field with one writer is fine.
6. **Single-owner writes and leaked seams.** Flag two modules writing the same
   external sink without a single owner or lease, or reaching into another
   module's private state instead of an explicit interface. For web UI code,
   also check [references/web-ui.md](references/web-ui.md).
7. **Resource symmetry and hot-path cost.** Every acquired resource (listener,
   observer, timer, subprocess, lock, abort handle) tears down symmetrically on
   close, re-entry, and interruption. On hot paths, flag hidden O(N) scans or
   expensive synchronous reads behind a cheap-looking interface.

Present candidates: files, problem, proposed change, benefit (locality, leverage,
tests), strength (strong, worth exploring, speculative). Ask which to explore
before proposing interfaces; findings are hypotheses and refactoring is the owner's call.

## Design it twice

For the chosen candidate, classify its dependencies: `in-process`, `local stand-in`,
`owned remote` (port plus adapters), `true external` (injected, mocked in tests).
Design two or three radically different interfaces (minimal entry points; most
common caller trivial; ports and adapters): spawn parallel `design` subagents
(`<this skill's directory>/scripts/role design`) for public, persistent, or core cross-cutting seams, and
sketch the contrasts inline yourself for local internal seams (parallel frontier
subagents reread the repo per launch). Compare on depth, locality and seam
placement, and recommend one, hybrid if better. Tests move to the new interface;
delete the old shallow tests they replace. A rejected candidate with a lasting
reason becomes an ADR, so the next survey does not suggest it again.
