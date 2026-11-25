---
name: rate
description: "Use whenever asked for a score or rating (\"rate X\", \"X out of 10\"), including \"fix it until 10/10\". Fixed rubric first, blind re-score by a fresh agent."
---

# Rate

## 1. Rubric first

Before looking for fixes, write six to eight criteria for what a 10 means here,
each with: what is judged (one line), the evidence (command, measurement, file,
or review), and what 0, 5 and 10 look like.

Weight criteria only if some clearly matter more. Show the rubric. Once scoring
starts it is fixed — moving goalposts invalidates the score. Add a missing
criterion only for the next round, explicitly.

## 2. Score

Score each criterion with its evidence, one line each, then the total:

```
<criterion>: <score>/10 - <what is missing for 10, concretely>
Total: <score>/10
```

If the user asked only for a rating, stop here.

## 3. Close the gaps

Fix the largest gaps first, following the matching skill ([tdd](../tdd/SKILL.md),
[debug](../debug/SKILL.md), [architecture](../architecture/SKILL.md)) and its
verification.

## 4. Re-score blind

The author of the fixes never grades them. A fresh cross-family agent (resolved
via `<this skill's directory>/scripts/role review --implementer-family <family>`)
gets only the artifact, the fixed rubric, and the evidence commands — never the
fix list or old scores. Its score is the result.

## 5. Stop

Stop when any of these holds:

- every criterion is 10 by the blind re-score;
- for each remaining point, the price (time, complexity, trade-offs) is named
  and the user decided it is not worth it;
- two to three fix and blind re-score rounds have run — pause, report the
  current blind score, per-criterion movement, and the concrete price of
  remaining points so the user decides whether to continue.

Any edit after the blind re-score, however small, voids it: re-score again.
Three rounds without movement on a criterion means the problem is structural:
say so and propose the larger change.

## Report

The rubric, first score, final blind score, per-criterion movement, fixes, and
the price of each point left on the table.
