# Model policy

[`models.toml`](models.toml) is the table machines read: role → model, effort,
fallback. This page is why. When a new model ships, change the table, run the
evals, and update the reasons here if they changed.

## Roles

| Role | First choice | Fallback | Why |
|---|---|---|---|
| design | Fable, high | Opus, high | Plans and interfaces decide what everything after them costs. The most expensive tokens go here, and to the final synthesis. |
| implement | Opus, high | Sol, xhigh | Implementation against a written contract is where most tokens go; a strong model with a clear brief is enough. |
| visual | Opus, high | none | Work judged by eye stays with the Anthropic family; its taste in layout has been more reliable. |
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
  deletion get reviewers from both families in parallel. Each has found real
  defects the other missed.
- **Quota decides the order, not taste.** Codex leads review and routine while
  at least 15% of its weekly limit is left, because its tokens are cheaper; below
  that, work moves to Claude so the last of the quota stays for review.
- **Subagents name their model.** A subagent inherits the session's model unless
  told otherwise, so a dozen research agents on the frontier model is waste.
  Give every delegated task the role's model explicitly.
- **Effort is part of the choice.** "Smart" Sol means `xhigh`; review runs at
  `medium` because a blind second opinion matters more than depth.

## Running a role

`[cli.*]` in the table gives the headless command for each CLI. Skills that
start another model (`cross-review`) and tools that run lanes read the role,
take the first choice whose conditions hold, and fill in `{id}` and `{effort}`.
