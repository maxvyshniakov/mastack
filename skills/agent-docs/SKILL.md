---
name: agent-docs
description: Use when writing, editing or auditing agent instructions (AGENTS.md, CLAUDE.md, skills, docs/agents), or after an agent ignored an instruction.
---

# Agent docs

## Writing

- **No-op test.** For every sentence: would a strong model do this without it?
  If yes, delete the sentence. Settle disagreements by running the document,
  not by arguing.
- **Say the target, not the ban.** A prohibition puts the forbidden behavior in
  context. State what to do; keep a "never" only as a hard guardrail, paired with
  the positive rule.
- **Rules over places.** "Every handler that mutates reports success" beats a
  list of three handlers; the fourth one is where the bug moves.
- **Reasons in one line.** Every rule a reader could not derive alone keeps
  its reason, in words: an incident, a constraint, a packaging fact. With the
  reason the next reader can judge an edge case instead of "fixing" the rule.
  A special case with no visible reason reads as an error.
- **One source of truth.** Each meaning in one place. A doc that restates the
  code, a config or `--help` is a cache that goes stale; keep only what cannot
  be looked up: conventions, reasons, gotchas.
- **Pointers decide reach.** A skill description or an AGENTS.md line is
  always loaded. Lead with the trigger words the user actually types, one per
  distinct case, nothing the body repeats.
- **Steps end on a checkable condition.** "Every modified file accounted for",
  not "review the changes".
- **Disclose by branch.** What every path needs stays in the file; what only
  some paths need goes to a linked reference file. Keep an always-loaded file
  (a SKILL.md body, AGENTS.md) within about 200 lines, and link references one
  level deep: a reference does not send the reader on to another reference.
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
- gaps against `CONTRACT.md`: missing `docs/agents/*.md`, or their content
  living elsewhere;
- no-op lines and prohibitions that should be positive rules;
- rules that could be checks;
- private details in files that will be published.

Each finding: file and line, the problem, the fix, the target file. Order by
how likely the defect is to mislead an agent today.
