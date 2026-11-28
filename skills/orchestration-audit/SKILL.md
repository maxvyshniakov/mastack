---
name: orchestration-audit
description: Use weekly, after a usage-limit spike, or before changing workflow settings (models per role, parallelism, checks, review depth). Audits token burn, orchestration mechanics, and cross-review yield across active providers, routing each finding to the layer that fixes it.
---

# Orchestration audit

Weekly retrospective on lane cost, orchestration mechanics, and review yield
across active providers (`claude-code`, `antigravity` / T3 Code; historical
`codex` when present). Read-only: change no project code; route findings to
tickets or settings.

**Scouting (Tier 3).** When an audit spans `>= 2` repositories or `> 25`
unknown candidate files, the audit lead may dispatch `1–3` parallel
pointer-only `scout` subagents (`<this skill's directory>/scripts/role scout` →
`sonnet`/`flash`, `<= 15` tool calls and `<= 2,500` chars output each,
`depth <= 1` — scouts never spawn children) returning `file:line` & count
manifests only, then **must** batch-read every load-bearing seam first-hand
before writing audit findings.

## Collect

1. Run `tokenfather report` for the target window and the prior week:

   ```bash
   tokenfather report --since <ISO-8601-start> [--until <ISO-8601-end>] [--project <name>] [--json]
   ```

   Flag any model falling back to `[pricing.default]` in `models.toml`.
2. Pull lane, check, and review aggregates:

   ```bash
   lanefather stats --json [--days <N>] [--lane <id>]
   ```

3. Note machine vs quota limits (Slotfather slot contention and load vs provider
   rate-limit hits).

## Questions

Answer each with tool numbers (never generalize from one session):

1. **Cost per landed lane and trend.** Weighted units and raw tokens per landed
   lane by provider vs the prior week.
2. **Context and turns by role.** Median/p90 context size and turns (coordinator
   vs subagents); share over `[providers.<family>]` budgets in `models.toml`
   (`reset_context_tokens` `150K`/`185K`, `max_turns_before_handoff` `80`).
3. **Cache behavior and warm hit rate.** Cache-read ratio and miss causes (idle
   past `[providers.<family>]` TTL, oversized outputs, cold restarts); warm
   resume vs fresh fix-round cost.
4. **Waiting and waste.** Turns spent polling (`lanefather list`, sleeps),
   `--help`, or repeated reads, grouped by command.
5. **Check runs and failure yield.** Runs/lane, duration, and failure yield from
   `lanefather stats`; flag full checks used as an edit loop.
6. **Orchestration mechanics.** Claim-conflict serialization, batch sizes
   (target 3–5 lanes), stale worktrees, `Garden` yield (kept vs dropped
   follow-ups), and owner questions history already answered.
7. **Review calibration (`cross-review`).** Findings/lane and rejected share by
   reviewer family and implementer model/effort; recurring `should have been
   caught by` promoted to checks; 1-in-5 post-hoc audit of exempt lanes.
8. **Parallelism bottleneck.** Machine-bound (slots, CPU/RAM) vs provider
   limit-bound.

## Route each finding

| Layer | Examples |
|---|---|
| Harness settings | Cache TTL, compaction threshold, default delegation options |
| Orchestrate & `models.toml` | Warm-vs-fresh rules, role/model/effort routing, `[pricing.*]` / `[providers.*]` |
| Project checks | Splitting focused checks from the full lane check in `docs/agents/checks.md`, running `test-audit` |
| Tools & hooks | `lanefather` stats/waits, `hooks/friction_hook.py` >8K journaling, `hooks/agent_role.py`, `tokenfather` attribution |

## Report

1. **Window & totals:** dates, providers, landed lanes, weighted units/lane and WoW delta.
2. **Answers:** one concise bullet or table row per question (1–8) with counts.
3. **Actions:** concrete ticket or setting change per finding (target layer, expected saving, owner decision?).
