---
name: orchestration-audit
description: Use weekly, after a usage-limit spike, or before changing workflow settings (models per role, parallelism, checks, review depth). Audits token burn, orchestration mechanics, and cross-review yield across active providers, routing each finding to the layer that fixes it.
---

# Orchestration audit

Weekly retrospective on lane cost, orchestration mechanics, and review yield
across active providers (`claude-code`, `codex`, `antigravity` / T3 Code).
Read-only: change no project code; route findings to tickets or settings.

## Collect

1. Run `tokenfather report` for the target window and the prior week:

   ```bash
   tokenfather report --since <ISO-8601-start> [--until <ISO-8601-end>] [--project <name>]
   tokenfather report --since <ISO-8601-start> [--until <ISO-8601-end>] [--project <name>] --json
   ```

   Flag any model falling back to `[pricing.default]` in `models.toml`.
2. Pull lane, check, and review aggregates from the lane tool:

   ```bash
   lanefather stats --json [--since <ISO-8601-start>] [--project <name>]
   ```

3. Note machine vs quota limits for the window (Slotfather slot contention and
   load vs provider rate-limit hits).

## Questions

Answer each with numbers from the tools (do not generalize from one session):

1. **Cost per landed lane and trend.** Weighted units and raw tokens per landed
   lane by provider, vs the prior week.
2. **Context and turns by role.** Median and p90 context size and turns for
   coordinator vs subagents; share exceeding `[providers.<family>]` budgets in
   `models.toml`.
3. **Cache behavior and warm-agent hit rate.** Cache-read ratio and what
   preceded misses (idle past `[providers.<family>]` TTL, oversized tool
   outputs, cold restarts); warm resume vs fresh fix-round cost.
4. **Waiting and waste.** Turns spent polling (`lanefather list`, sleeps),
   `--help`, or repeated reads, grouped by command.
5. **Check runs and failure yield.** Runs per lane, duration, and failure yield
   from `lanefather stats`. Flag full checks used as an edit loop.
6. **Orchestration mechanics.** Claim-conflict serialization overhead, batch
   sizes (target 3–5 lanes), stale worktrees, and owner questions that history
   already answered.
7. **Review calibration (`cross-review`).** Findings per lane and rejected
   share by reviewer family and implementer model/effort; whether recurring
   `should have been caught by` entries became mechanical checks; whether the
   1-in-5 post-hoc audit of exempt lanes ran.
8. **Parallelism bottleneck.** Machine-bound (slots, CPU/RAM) vs provider
   limit-bound.

## Route each finding

Route each root cause to the cheapest layer that fixes it:

| Layer | Examples |
|---|---|
| Harness settings | Cache TTL, compaction threshold, default delegation options |
| Orchestrate & `models.toml` | Warm-vs-fresh rules, role/model/effort routing, `[pricing.*]` / `[providers.*]` |
| Project checks | Splitting focused checks from the full lane check in `docs/agents/checks.md`, running `test-audit` |
| Tools & hooks | `lanefather` stats/waits, `hooks/friction_hook.py` >8K journaling, `hooks/agent_role.py`, `tokenfather` attribution |

## Report

1. **Window & totals:** dates, providers, landed lanes, weighted units per lane
   and week-over-week delta.
2. **Answers:** one concise bullet or table row per question (1–8) with counts.
3. **Actions:** one concrete ticket or setting change per finding, with target
   layer, expected saving, and whether it needs an owner decision.
