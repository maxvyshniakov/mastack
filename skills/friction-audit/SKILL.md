---
name: friction-audit
description: Use when agents keep misusing a package or product, or before revising its API or docs. Routes each kind of confusion to lint, API, docs, skill or test.
---

# Friction audit

A retro on a product, not on a session. The question: what do agents keep
getting wrong when they use this, and which layer would stop it.

## Sources

Start with the **friction journal**, then inspect the rest with a read-only
`scout` subagent (`bin/role scout`) and keep raw counts.

- **The journal** (`$XDG_STATE_HOME/friction/events.jsonl`; `hooks/friction_journal.py`):
  run `bin/friction scan` first, then rank with
  `bin/friction report [--package <name>] [--since <period>]` (separates
  `large-bash-output` noise by default; `--include-tool-noise` ranks it inline)
  or `repo-kit friction report --package <name> --since <period>`. Include
  coworkers' `repo-kit friction export` bundles. Follow each event's `why`, file
  and session into transcripts only where needed.
- **Lint baselines**: structured entries (`category`, `component`, `remove`)
  count missing APIs and unclear docs.
- **Agent transcripts** touching the package: ignored lint messages, added
  suppressions, questions asked, hand-rebuilt features, and user corrections.
- **Consumer code**: overrides and `!important`, internal selectors, component
  wrappers, local copies, suppressions, unmarked `UPSTREAM(...)` workarounds.
- **Bug history**: fixed changelog entries and closed issues grouped by kind — a
  recurring kind is a missing guard, not bad luck.

Verify every finding against the current version before counting it. Name any
producer gap (hook, scanner, lint) when transcripts show a class the journal missed.

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
