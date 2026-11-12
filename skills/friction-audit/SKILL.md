---
name: friction-audit
description: Use when agents keep misusing a package or product, or before revising its API or docs. Routes each kind of confusion to lint, API, docs, skill or test.
---

# Friction audit

A retro on a product, not on a session. The question: what do agents keep
getting wrong when they use this, and which layer would stop it.

## Sources

Start with the **friction journal**, then read the rest with a subagent
(`research` role) and keep raw counts.

- **The journal** (`$XDG_STATE_HOME/friction/events.jsonl`; see
  `hooks/friction_journal.py`): lint findings beyond the baseline, type errors
  on the package's types, the owner's `/friction` corrections, corrections and
  misuse the session scanner found, vendored-copy patches. Rank it with
  `repo-kit friction report --package <name> --since <period>`, or read the
  JSONL. Run `bin/friction scan` first so the newest sessions are in. Each
  event's `why`, file and session point at the evidence; read the transcript
  only there and for the sources below that the journal does not cover.
  Coworkers' `repo-kit friction export` bundles count the same way.
- **Lint baselines**: structured entries (`category`, `component`, `remove`)
  are a list of missing APIs and unclear docs by count.
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
already fixed. A class the transcripts show but the journal missed is a gap in
a producer (hook, scanner, lint): name it in the report.

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
