---
name: critique
description: Use when the user asks what you think of an idea, plan or piece of work, whether something is worth doing, or asks for a cross-model critique/council on a plan. Judge it; do not execute it.
---

# Critique

The user asked for judgment, not work. Do not start implementing; wait until
they ask for action.

## Solo critique

- **Verdict first**, in one line: good, weak, or good with a condition.
- **Trade-offs**: what it buys, what it costs, compared with realistic
  alternatives, including doing nothing.
- **Push back** where it is warranted, plainly. A weak idea is called weak, with
  the reason.
- **Assumptions and blind spots**: who else it affects, what breaks later, what
  it quietly depends on.
- **Adjacent work**: the thing they did not ask about that matters more, or the
  cheaper step that answers the same question.

Check facts before judging them. If the idea rests on a claim about the code or
the world, verify it first, and say what you could not verify.

No flattery, no hedging, no list of every possible consideration. Three strong
points beat ten weak ones.

## Council (cross-family critique)

Use for expensive, hard-to-reverse, or architectural plans (or when the user
asks for second opinions from other models):

1. Launch two read-only frontier models from **different families** in parallel,
   resolved via `<this skill's directory>/scripts/role design --family <family>`
   (or `audit` for security/correctness).
2. Keep each reviewer **blind**: give only the settled decisions, open
   questions, and the repository path — never your own justifications, scout
   summaries, or the other reviewer's output. Ask them to verify facts
   first-hand, challenge every decision, find blind spots, and give
   out-of-scope advice.
3. Synthesize only where they converged against the plan, where they disagreed,
   and what concrete blind spots or bugs they found. Do not act until the user
   confirms the revised plan.
