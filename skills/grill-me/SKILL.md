---
name: grill-me
description: Use when asked to grill the user on a plan, or when a plan has unresolved decisions. One question at a time, each with a recommended answer.
---

# Grill me

Reach a shared understanding of the plan before anyone builds it.

## The tree

Every decision branches into dependent decisions. The **frontier** is the open
decisions whose prerequisites are settled; ask only from the frontier.

## One question at a time

Ask the most consequential frontier question, then stop and wait (batch only if
the user asks):

```
**Q3. <title>**
<the question, options if any, what each costs>

Recommendation: <your answer and reason>
```

## Facts are yours, decisions are theirs

Look up anything the code, docs, tracker or tools can answer, using parallel
read-only `scout` subagents (`bin/role scout`) when starting on an existing
repository (code, open issues, recent history). Never ask the user a fact you
could find. Put every real choice to them with your recommendation; do not
reopen settled decisions or turn delegated technical details into approval gates.

Test claims against the code. When the user's description disagrees with the
code, say so with `file:line`.

## Write it down as you go

- **Terms.** Add precise meanings for fuzzy or overloaded words to the glossary
  in `docs/agents/domain.md` at once — definitions only, no implementation detail.
- **ADRs.** Offer one only for a hard-to-reverse, non-obvious trade-off; one
  paragraph (context, decision, why) is enough.

No repository to write into: track agreed terms and decisions in the
conversation and list them at the end.

## Questionnaire mode

When answers live with someone else, ask the user only the recipient and needed
outcome, then write the questionnaire: purpose, brief context, questions most
important first (one idea each) with an empty answer slot under each.

## Done

When all decisions in scope are settled, summarize them and ask the user to
confirm. For expensive or architectural plans, offer one blind cross-family
[critique](../critique/SKILL.md#council-cross-family-critique) (council mode)
before [to-spec](../to-spec/SKILL.md) so another model family checks the plan
against the raw repository. Wait for confirmation unless building was already asked.
