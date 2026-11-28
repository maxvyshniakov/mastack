---
name: critique
description: Use when the user asks what you think of an idea, plan or piece of work, whether something is worth doing, or asks for a cross-model critique/council on a plan. Judge it; do not execute it.
---

# Critique

The user asked for judgment, not work. Wait until they ask for action before
implementing.

## Solo critique

- **Verdict first**, in one line: good, weak, or good with a condition.
- **Trade-offs**: what it buys and costs versus realistic alternatives, including
  doing nothing.
- **Push back** plainly where warranted; call a weak idea weak and say why.
- **Assumptions and blind spots**: who else it affects, what breaks later, what
  it quietly depends on.
- **Adjacent work**: what matters more that they did not ask about, or the
  cheaper step that answers the same question.

Verify code or world claims before judging them, and state what you could not
verify. Three strong points beat ten weak ones; skip flattery and hedging.

## Council (cross-family critique)

Use for expensive, hard-to-reverse, or architectural plans (or when the user
asks for second opinions from other models):

1. Launch two read-only frontier models from **different families** in parallel,
   resolved in one call via `<this skill's directory>/scripts/role critique --pair`
   (or `audit --pair` for security/correctness; pass `--exclude-family` if a
   provider is unavailable). Outside T3 Code where `delegate_task` is
   unavailable for a second family, fall back to one fresh cross-family `review`
   role or solo critique.
2. Keep each reviewer **blind** and flat (**Tier 2: `0` sub-scouts, `depth <= 1`**):
   pass only the settled decisions, open questions, and repository path — never
   your own justifications, scout summaries, or the other reviewer's output.
   Council members must not spawn child subagents; they verify codebase claims
   first-hand via batched parallel whole-file reads/greps, challenge every
   decision, find blind spots, and give out-of-scope advice.
3. Synthesize only where they converged against the plan, where they disagreed,
   and concrete blind spots or bugs found. Do not act until the user confirms.
