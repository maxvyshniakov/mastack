---
name: grill-me
description: Use when asked to grill the user on a plan, or when a plan has unresolved decisions. One question at a time, each with a recommended answer.
---

# Grill me

Reach a shared understanding of the plan before anyone builds it.

## The tree

Every decision branches into the decisions that depend on it. The **frontier**
is the open decisions whose prerequisites are settled. Ask from the frontier
only; a question whose answer depends on another open question waits.

## One question at a time

Ask the most consequential frontier question, then stop and wait.

```
**Q3. <title>**
<the question, options if there are any, what each one costs>

Recommendation: <your answer and the reason>
```

Ask several at once only when the user asks for a batch.

## Facts are yours, decisions are theirs

Look up anything the code, docs, tracker or tools can answer, using subagents
for wider searches. Never ask the user a fact you could find. Put every real
choice to them, with your recommendation. Do not reopen what they settled, and
do not turn technical details they delegated to you into approval gates.

Test claims against the code. When the user says how something works and the
code disagrees, say so with the file and line.

## Write it down as you go

- **Terms.** When a fuzzy or overloaded word gets a precise meaning, add it to
  the glossary named in `docs/agents/domain.md` at once. Definitions only, no
  implementation detail.
- **ADRs.** Offer one only when a decision is hard to reverse, surprising
  without context, and the result of a real trade-off. One paragraph is enough:
  context, decision, why.

No repository to write into: keep the agreed terms and decisions in the
conversation and list them at the end.

## Questionnaire mode

When the answers live in someone else's head, ask the user only who it goes to
and what they need back. Then write a questionnaire for that person: purpose,
short context, questions most important first, one idea each, an empty answer
under each.

## Done

When the decisions this scope needs are settled, summarise them and ask the user
to confirm. Do not act on the result until they do, unless they already asked
for it to be built.
