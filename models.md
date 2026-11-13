# Model policy

[`models.toml`](models.toml) is the table machines read: role → model, effort,
fallback. This page is why. When a new model ships, change the table, run the
evals, and update the reasons here if they changed.

## Roles

| Role | First choice | Fallback | Why |
|---|---|---|---|
| design | Fable, high | Opus, high | Plans and interfaces decide what everything after them costs. The most expensive tokens go here, and to the final synthesis. |
| implement | Opus, medium | Sol, xhigh | Implementation against a written contract is where most tokens go; a strong model with a clear brief is enough. |
| visual | Opus, high | none | The author prefers to keep work judged by eye with the Anthropic family. |
| review | Sol, medium | Opus, medium | The reviewer is of another family than the implementer, so it does not share the implementer's blind spots. |
| routine | Sol, medium | Opus, medium | Bulk, low-risk work: renames, mirroring docs, running checks. |
| research | Opus, medium | Sonnet, medium | Collecting facts needs care, not frontier judgment. Sonnet only for plain reading and search. |
| audit | Fable, high | Opus, high | A finding from a cheaper model is a lead until a strong model has verified it. |

## Rules behind the table

- **Review crosses families.** Two models of one family miss the same things.
  When the other family is out of quota, a same-family reviewer in a fresh
  context is the fallback, and the report says so.
- **Review is bounded.** One review, one round of fixes, every finding marked
  fixed or rejected. A strong reviewer can find something forever; a second
  round rarely pays for itself.
- **Both lenses for dangerous surfaces.** Migrations, auth, money and
  deletion get reviewers from both families in parallel, on the author's view
  that two families are likely to catch different defects.
- **Quota decides the order, not taste.** Codex leads review and routine while
  at least 15% of its weekly limit is left, because its tokens are cheaper; below
  that, work moves to Claude so the last of the quota stays for review.
- **Subagents name their model.** A subagent inherits the session's model unless
  told otherwise, so a dozen research agents on the frontier model is waste.
  Give every delegated task the role's model explicitly.
- **Effort is part of the choice.** "Smart" Sol means `xhigh`; review runs at
  `medium` because a blind second opinion matters more than depth.

## Running a role

`bin/role <role> [--implementer-family F] [--json]` decides, so nobody reads
the table by eye: it takes the role's first choice whose conditions hold,
reading each quota a condition names live (`codex_weekly`: `codex app-server`,
`account/rateLimits/read`), and prints the model, id, family, effort, each
command of its `[cli.*]` with `{id}` and `{effort}` filled, its note, and why
every earlier choice was skipped:

```
$ bin/role review --implementer-family anthropic
review: opus (claude-opus-5-5, anthropic), effort medium
  run: claude -p --model claude-opus-5-5 --effort medium
  review: claude -p --model claude-opus-5-5 --effort medium
  note: same family as the implementer: fresh context only, say so in the report
skipped:
  sol: codex_weekly 0% left, needs 15%
  opus: same family as the implementer (anthropic)
```

A quota it cannot read (no `codex`, no answer) counts as not met and is named.
`not_family` is not met without `--implementer-family`. Exit 1 when no choice
qualifies, 2 when the table or the role cannot be read. `MASTACK_MODELS` names
another table. Skills that start another model (`cross-review`, `orchestrate`,
`research`, `rate`) run it and use its answer.

The Bash hook's `codex_credits` check holds the quota rule where no skill is
read: it refuses a headless `codex exec` or `codex review` while the weekly
limit is under the review role's threshold, naming what `role review` picks
instead. `MASTACK_ALLOW_CREDITS=1` before the command is the owner's override.
