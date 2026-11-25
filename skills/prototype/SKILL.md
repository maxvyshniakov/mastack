---
name: prototype
description: Use when asked for a prototype or design variants, or when a state model or screen needs trying before it is built. Throwaway code only.
---

# Prototype

Throwaway code that answers one question. Write the question at the top of the
prototype, visibly, so the answer can be checked against it.

## Logic or state

"Does this model handle X then Y?"

- Put logic in one pure module (reducer `(state, action) => state`, explicit
  state machine, or pure functions — no DOM) so it lifts into real code unchanged.
- Wrap in one self-contained HTML file that opens by double-click (no build,
  server, or dependencies), using non-coder domain labels.
- Layout: the question; full current state as labelled fields re-rendered after
  every action with changes marked; one button per action; guided scenario tabs
  (happy path, awkward edge case, attempted illegal action) from known states.

## UI

"What should this look like?"

- Three radically different variants by default (five max), not shades of one idea.
- Mount on the real page with real data, header and density, switched by
  `?variant=` and a small floating bar (a throwaway route is last resort; an
  empty page hides problems). Reuse the project's routing and components.

## Rules for both

- Named so nobody mistakes it for production; next to the code it explores.
- One command or double-click to open it.
- State in memory (or a clearly named scratch store if persistence is the question).
- No tests, no error handling beyond keeping it running, no abstractions.

## When it has answered

Record the verdict and settled question on the issue. Rebuild the validated
decision into real code via [tdd](../tdd/SKILL.md). Archive the prototype on its
own branch linked from the issue so it stays a primary source outside the product.
