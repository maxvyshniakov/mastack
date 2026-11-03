---
name: friction-audit
description: Use when agents keep misusing a package or product, or before revising its API or docs. Routes each kind of confusion to lint, API, docs, skill or test.
---

# Friction audit

A retro on a product, not on a session. The question: what do agents keep
getting wrong when they use this, and which layer would stop it.

## Sources

Read each with a subagent (`research` role) and keep raw counts.

- **Agent transcripts** that touch the package: rule violations and the lint
  messages agents ignored, suppressions they added, questions they asked,
  things they rebuilt by hand that the package already has, corrections from
  the user.
- **Consumer code**: overrides and `!important`, selectors into internals,
  wrappers around components, local copies of package code, suppression
  comments, workarounds without an `UPSTREAM(...)` mark.
- **Bug history**: fixed entries in the changelog and closed issues, grouped by
  kind. A kind that recurs is a missing guard, not bad luck.

Check every finding against the current version before counting it; some are
already fixed.

## Classify

Group findings into **classes**, each a shared cause, not a symptom. For each
class, pick the layer that would change agent behavior, cheapest that works:

| Layer | When it fits |
|---|---|
| Lint or check | A mechanical pattern; the message names the right prop or component |
| API or default | Agents keep writing the same workaround; the package should do it |
| Contract test or matrix | Sibling components drift apart; one guard covers the family |
| Public hook manifest | Consumers rely on internals; make them stable or forbid them |
| Docs or index | The thing exists and agents do not find it |
| Consumer skill | A judgment call no check can make |

Lint warnings that agents see in every session stop working; prefer a ratchet
(new violations fail, old ones are listed with reasons) over more warnings.

## Report

Per class: evidence with counts and links, the layer, the change, priority, and
whether it is an owner decision (API, visuals, breaking changes). Findings are
hypotheses until reproduced; each fix starts with a reproduction and ends with
a guard that turns the next instance red.
