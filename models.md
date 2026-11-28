# Model policy

[`models.toml`](models.toml) is the table machines read: active families, role →
model, effort, fallback, and per-provider cache/context ceilings. This page is
why. When a new model ships, change the table, run the evals, and update the
reasons here if they changed.

Active families are **`anthropic`** and **`google`** (`active_families = ["anthropic", "google"]`).
`sol` / `codex` (`openai`) is retired; `bin/role` spawns no `codex app-server`
process, and `hooks/codex_credits.py` denies headless `codex` runs immediately
unless `MASTACK_ALLOW_CREDITS=1` is prefixed.

## Roles

| Role | First choice | Fallbacks | Why |
|---|---|---|---|
| implement | Neon, medium | Opus, medium; Argon, medium | Structural, architectural, and regular code against a spec or ticket contract. |
| visual | Opus, high | Neon, high | UI, layout, styling, and anything judged visually (`only_families = ["anthropic", "google"]`). |
| review | Carbon, medium | Fable, high | Independent blind cross-family review (`not_family = true`), falling back to same-family in a fresh context with a note. |
| critique | Carbon, high | Fable, high | Challenging plans, trade-offs, and architectural proposals without executing them; Council runs both via `--pair`. |
| specify | Carbon, high | Fable, high | Specs, pre-lane Specifier notes, and mid-flight Advisor calls. |
| design | Carbon, high | Fable, high | Interface design, architecture synthesis, and judgment calls (alias-compatible with `specify`). |
| audit | Carbon, high | Fable, high | Security, correctness, test, friction, and orchestration audits. |
| scout | Sonnet, medium | Flash, medium | Read-only repository mapping, call-site discovery, and doc/changelog verification (`forbid_models` blocks frontier/strong models). |
| routine | Sonnet, medium | Argon, medium; Flash, medium | Token-heavy, low-risk mechanical edits, renames, running checks, and doc mirroring (`forbid_models` blocks `opus`/`neon`/`fable`/`carbon`). |
| research | Argon, medium | Sonnet, medium; Flash, medium | Reading docs and primary sources, collecting facts and release notes (`forbid_models` blocks `opus`/`neon`/`fable`/`carbon`). |

## Rules behind the table

- **Two active families (`anthropic`, `google`).** Every model in
  `[roles.*.choices]` must belong to `active_families`; placing an inactive
  family in a role raises `TableError` at load time.
- **Review crosses families.** Two models of one family miss the same things.
  `--implementer-family google` routes review to plain `fable` (`high`, no
  extra brief guard); `--implementer-family anthropic` routes review to `carbon`
  (`medium`). When no other family is available, a same-family reviewer in a
  fresh context is the fallback, and the report says so.
- **Review is bounded.** One review, one round of fixes, every finding marked
  fixed or rejected. A strong reviewer can find something forever; a second
  round rarely pays for itself.
- **Both lenses for dangerous surfaces and Council critiques.** Migrations,
  auth, money, deletion, and Council plan critiques use `bin/role <role> --pair`
  to resolve a `(primary, partner)` pair from two distinct active families.
- **Economy roles forbid frontier models.** `scout`, `routine`, and `research`
  declare `forbid_models = ["opus", "neon", "fable", "carbon"]`, enforced at
  table load time so cheap mechanical work never silently drifts onto `0.8–1.0×`
  models.
- **Subagents name their model.** A subagent inherits the session's model unless
  told otherwise, so a dozen research agents on the frontier model is waste.
  Give every delegated task the role's model explicitly.
- **Effort is part of the choice.** Each provider names its reasoning option
  differently (`effort` for Claude, `thought_level` for Antigravity / Google).
  Single-lane `review` uses `carbon` at `medium` or `fable` at `high`;
  high-leverage judgment (`critique`, `specify`, `design`, `audit`) runs at
  `high`.
- **Cache windows and context budgets live in `[providers.<family>]`.** Skills
  and coordinators read `cache_ttl_minutes`, `subagent_cache_ttl_minutes`,
  `warm_idle_minutes`, `warm_context_tokens`, `reset_context_tokens`, and
  `max_turns_before_handoff` per active provider instead of assuming one
  provider's TTL or compaction ceiling.

## Judgment scout policy

Judgment models (`carbon`, `fable`) follow a three-tier boundary for spawning
economy `scout` subagents (`sonnet`/`flash`, `0.1–0.2×`):

- **Tier 1 — Single-lane `review` and mid-flight Advisor (`0` scouts):**
  Reviewers and mid-flight Advisors never spawn child subagents (`scout_budget = 0`,
  `depth <= 1`). They read every changed file and immediate caller first-hand
  in batched parallel whole-file reads (up to the ~800-line tool cap). When a
  `cross-review` needs mechanical doc or changelog verification, the coordinator
  spawns that `scout` sibling flat beside the reviewer.
- **Tier 2 — Delegated Council `critique` (`0` sub-scouts by default):**
  Blind Council reviewers (`bin/role critique --pair`) execute flat (`depth <= 1`,
  `0` child subagents) and verify codebase claims first-hand in batched reads so
  two Council members never duplicate scouting passes or filter subtle seams
  through lossy summaries.
- **Tier 3 — Wide `specify` / `design` / `audit` (`1–3` pointer-only scouts):**
  Only when target files are unknown across `>= 2` repositories or `> 25`
  candidate files (or when a brief explicitly grants `Scout budget: 1..3`), a
  judgment lead may dispatch `1–3` parallel `scout` subagents (`bin/role scout`,
  `<= 15` tool calls and `<= 2,500` chars output each, `depth <= 1` — scouts
  never spawn children):
  - **Pointer-only output:** scouts return fact manifests (`file:line` pointers,
    symbol/call-site lists, config keys, raw counts) — never defect verdicts,
    severity ratings, or design proposals.
  - **Mandatory first-hand verification:** the judgment model must batch-read
    every load-bearing `file:line` seam first-hand before writing a spec
    contract, architectural decision, or audit finding.

## Running a role

`bin/role <role> [--implementer-family F] [--family F] [--exclude-family F] [--pair] [--json]`
decides, so nobody reads the table by eye: it takes the role's first choice
whose conditions hold and prints the model, id, family, effort, each command of
its `[cli.*]` with `{id}` and `{effort}` filled (or the `delegate_task` target
and `thought_level` option for Antigravity), its note, and why every earlier
choice was skipped:

```
$ bin/role review --implementer-family anthropic
review: carbon (gemini-4-carbon, google), effort medium
  delegate_task: target.model="gemini-4-carbon", target.options.thought_level="medium"
```

With `--exclude-family google` as well, it falls back to same-family `fable`
with the fresh-context note.

For Council critiques or two-family panels, `--pair` resolves two distinct
active families in one call (exiting `1` if cooldowns or exclusions leave fewer
than two qualifying families):

```
$ bin/role critique --pair
critique (pair):
  primary: carbon (gemini-4-carbon, google), effort high
    delegate_task: target.model="gemini-4-carbon", target.options.thought_level="high"
  partner: fable (claude-fable-5-2, anthropic), effort high
    run: claude -p --model claude-fable-5-2 --effort high
    review: claude -p --model claude-fable-5-2 --effort high
```

`not_family` is not met without `--implementer-family`, and the answer then
carries a caution. Exit 1 when no choice (or second family for `--pair`)
qualifies, 2 when the table or the role cannot be read. `MASTACK_MODELS` names
another table. Skills that start another model (`cross-review`, `orchestrate`,
`research`, `rate`, `critique`) run it through `scripts/role` in their own
directory, a link to `bin/role`, and use its answer.

The Bash hook's `codex_credits` check denies headless `codex exec`, `codex e`,
and `codex review` immediately with zero subprocess latency whenever `openai` is
absent from `active_families` (or `[cli.codex]` is absent), naming
`bin/role <role>` as the replacement. `MASTACK_ALLOW_CREDITS=1` before the
command is the owner's override (logged to `guard.log`).
