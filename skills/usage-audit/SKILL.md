---
name: usage-audit
description: Use weekly, after a usage-limit spike, or before changing workflow settings (models per role, parallelism, checks). Runs tokenfather report across Claude Code, Codex and Antigravity / T3 Code, answers the audit questions, and routes each finding to the layer that fixes it.
---

# Usage audit

A repeatable retrospective on token usage, quota burn, and lane cost across
every active provider (`claude-code`, `codex`, `antigravity` / T3 Code). Run it
weekly, after a limit spike, and before changing models per role, parallelism,
or project check chains.

## Collect

1. Run `tokenfather report` for the target window (and the prior week for trend
   comparison):

   ```bash
   tokenfather report --since <ISO-8601-start> [--until <ISO-8601-end>] [--project <name>]
   tokenfather report --since <ISO-8601-start> [--until <ISO-8601-end>] [--project <name>] --json
   ```

   `tokenfather` collects transcripts from `claude-code`, `codex`, and
   `antigravity` (including T3 Code sessions), attributes requests to lanes,
   and applies the per-model price weights in `models.toml` (`[pricing.*]`).
   If a model shows up with default weights, add or update its `[pricing.<model>]`
   entry in `models.toml`.
2. Pull lane check and review stats from the lane tool:

   ```bash
   lanefather stats [--since <ISO-8601-start>] [--project <name>]
   ```

3. Note the machine and quota state for the window: active Slotfather slots and
   load peaks vs provider rate-limit hits (Claude weekly, Codex weekly,
   Antigravity / Gemini limits).

## Questions

Answer every question with numbers from the report (do not guess or generalize
from one session):

1. **Cost per landed lane and weekly trend.** Weighted units (and raw tokens)
   per landed lane, split by provider (`claude-code`, `codex`, `antigravity`),
   and how the current week compares with previous weeks.
2. **Context per turn and turns per lane, by role.** Median and p90 context
   size and turns per lane for `main` (coordinator) vs `subagent`
   (implementers, reviewers, scouts). Report what share of turns exceed each
   provider's compaction or warm-context budget (`[providers.<family>]` in
   `models.toml`).
3. **Cache misses and cache behavior per provider.** Cache-read ratio, cache
   misses, and what preceded them (idle gaps past the cache window, fresh
   restarts, prompt churn, large tool outputs). Check provider-specific
   mechanics rather than assuming one TTL:
   - **Claude Code (`anthropic`)**: whether subagents ran with the 1h TTL
     (`CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL`) or fell back to 5m writes.
   - **Codex (`openai`)**: automatic cache hit rate across its ~5-10m window.
   - **Antigravity / T3 Code (`google`)**: implicit cache hit rate and warm
     session reuse across delegated turns.
4. **Waiting turns and what they wait for.** Turns spent polling lane/check
   status (`lanefather list`, sleep loops), opening `--help`, or running tiny
   repeated reads, grouped by tool and command.
5. **Check runs per lane.** Count of check runs per lane, their duration, and
   their failure yield (from `lanefather stats`). Flag lanes running full
   browser or gate chains during the edit-check loop instead of focused checks
   plus one lane check on the committed tree.
6. **Usage by model and reasoning option per role, and quality trade-off.**
   Weighted usage by `(provider, model, effort / model_reasoning_effort /
   thought_level)` per role, paired with review findings per lane grouped by
   implementer model. Call out whether a cheaper model or lower reasoning level
   increased review findings or fix-round cost.
7. **Review yield.** Review findings per lane, rejected share, and the weighted
   cost of the fix round (comparing warm resume vs fresh fix-round agents).
8. **Parallelism bottleneck.** Whether throughput in the window was bound by
   the machine (Slotfather slots, CPU/memory load, check contention) or by a
   provider usage limit.

## Route each finding

Group causes (not individual symptoms) and route every finding to the cheapest
layer that fixes it:

| Layer | When it fits | Examples |
|---|---|---|
| Harness settings | Cache TTL, compaction threshold, provider runtime or T3 Code / Antigravity session defaults | Enabling 1h subagent TTL in Claude Code, raising/tuning compaction window, default delegation options |
| Orchestrate skill & model policy | Agent reuse, scouting, fix-round policy, brief discipline, role/model/effort routing | Tightening warm-vs-fresh rules in `orchestrate`, shifting `scout`/`routine` to cheaper models or another provider in `models.toml`, updating `[pricing.*]` or `[providers.*]` |
| Project checks | Slow or noisy check chains, low-yield browser runs on every edit | Splitting focused checks from the full lane check in `docs/agents/checks.md`, running `test-audit` |
| Tools & hooks | Polling, `--help` loops, oversized tool output, missing model/option guards | Adding `lanefather wait`, improving CLI errors, journaling oversized Bash output (>8K) in `hooks/friction_hook.py`, `hooks/agent_role.py` coverage, `tokenfather` attribution gaps |

## Report

Keep the report short and scannable:

1. **Window & totals**: dates, providers covered, landed lanes, total weighted
   units, and weighted units per landed lane (with week-over-week delta).
2. **Answers**: one concise bullet or table per question (1-8) with the exact
   numbers.
3. **Actions**: one concrete ticket or setting change per finding, naming the
   target layer, the expected saving, and whether it needs an owner decision
   (model/quality trade-offs, budget caps, or breaking workflow changes).
