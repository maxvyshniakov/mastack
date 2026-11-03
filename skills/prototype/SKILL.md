---
name: prototype
description: Use when asked for a prototype or design variants, or when a state model or screen needs trying before it is built. Throwaway code only.
---

# Prototype

Throwaway code that answers one question. Write the question at the top of the
prototype, visibly, so the answer can be checked against it.

## Logic or state

"Does this model handle X then Y?"

- Put the logic in one pure module: a reducer `(state, action) => state`, a
  state machine with explicit transitions, or pure functions over a data type.
  No DOM inside it; it should lift into the real code unchanged.
- Wrap it in one self-contained HTML file that opens by double-click: no build,
  no server, no dependencies.
- Labels in domain language, readable by someone who does not code.
- Layout: the question; the full current state as labelled fields, re-rendered
  after every action with the change marked; one button per action; tabs of
  guided scenarios (happy path, the awkward edge case, an attempt at something
  that must be illegal), each starting from a known state.

## UI

"What should this look like?"

- Three variants by default, five at most, each radically different, not three
  shades of one idea.
- Mount them on the real page they belong to, with real data, header and
  density, switched by a `?variant=` search parameter and a small floating bar.
  A new throwaway route is the last resort; an empty page hides problems.
- Follow the project's routing and component conventions; reuse its components.

## Rules for both

- Named so nobody mistakes it for production; next to the code it explores.
- One command to start it.
- State in memory. If persistence is the question, a scratch store whose name
  says to wipe it.
- No tests, no error handling beyond what keeps it running, no abstractions.

## When it has answered

Record the verdict and the question it settled on the issue. Move the
validated decision into the real code through `tdd`. Commit the prototype to its
own branch, out of the main line, and link that branch from the issue, so it
stays a primary source without living in the product.
