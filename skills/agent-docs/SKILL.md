---
name: agent-docs
description: Use when writing, editing or auditing agent instructions (AGENTS.md, CLAUDE.md, skills, docs/agents), or after an agent ignored an instruction.
---

# Agent docs

## Writing

- **No-op test.** For every sentence: would a strong model do this without it?
  If yes, delete it. Settle disagreements by running the document, not arguing.
- **Say the target, not the ban.** A prohibition puts the forbidden behavior in
  context. State what to do; keep a "never" only as a hard guardrail, paired with
  the positive rule.
- **Rules over places.** "Every handler that mutates reports success" beats a
  list of three handlers; the fourth one is where the bug moves.
- **Reasons in one line.** Every rule a reader could not derive alone keeps its
  reason in words (incident, constraint, packaging fact) so the next reader can
  judge edge cases instead of "fixing" a special case that looks like an error.
- **One source of truth.** Each meaning in one place. A doc that restates the
  code, a config or `--help` is a cache that goes stale; keep only what cannot
  be looked up: conventions, reasons, gotchas.
- **Pointers decide reach.** A skill description or an AGENTS.md line is
  always loaded. Lead with the trigger words the user actually types, one per
  distinct case, nothing the body repeats.
- **Steps end on a checkable condition.** "Every modified file accounted for",
  not "review the changes".
- **Disclose by branch.** Keep what every path needs in the always-loaded file
  (`SKILL.md` body, `AGENTS.md`; ≤200 lines) and move branch-only detail to a
  linked reference one level deep (references do not link to other references).
- **Mechanical rule, mechanical check.** A fixed pattern belongs in a lint
  rule, hook or test, not in prose.

## Auditing

Read every agent-facing file in scope and report:

- broken links, paths and commands that no longer exist;
- rules and special cases without a reason a reader could judge by;
- always-loaded files over about 200 lines, and references nested deeper than one link;
- contradictions between copies of the same rule, with the canonical copy;
- facts duplicated across files, and where each belongs;
- stale facts against the current code and tools;
- gaps against `CONTRACT.md`: missing `docs/agents/*.md` required by the
  project's workflow, or contract facts duplicated in `AGENTS.md` or elsewhere;
- no-op lines and prohibitions that should be positive rules;
- rules that could be checks;
- private details in files that will be published.

Each finding: `file:line`, problem, fix, target file; ordered by how likely the
defect is to mislead an agent today.
