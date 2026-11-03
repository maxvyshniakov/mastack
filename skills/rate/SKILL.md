---
name: rate
description: Rate anything out of 10 against a rubric fixed before any change - code, tests, docs, an API, CI, a skill - and, when asked, improve it until 10/10 with a blind re-score by a fresh agent. Use for every request for a score or rating, "rate X", "how good is", "на сколько из 10?", "оцени из 10", "поставь оценку", "чини, пока не 10/10".
---

# Rate

## 1. Rubric first

Before looking for fixes, write six to eight criteria for what a 10 means for
this kind of thing, each with:

- what is judged, in one line;
- the evidence that shows it (a command, a measurement, a file, a review);
- what 0, 5 and 10 look like.

Weight criteria only if some clearly matter more. Show the rubric. Once scoring
starts it is fixed; moving the goalposts after seeing the work makes the score
meaningless. A criterion found missing later is added for the next round and
said so, never swapped in silently.

## 2. Score

Score each criterion with its evidence, one line each, then the total:

```
<criterion>: <score>/10 - <what is missing for 10, concretely>
Total: <score>/10
```

If the user asked only for a rating, stop here.

## 3. Close the gaps

Fix the largest gaps first. Each fix is ordinary work under its own skill
(`tdd`, `debug`, `architecture`) and verified the way that skill says.

## 4. Re-score blind

The one who made the fixes does not grade them. A fresh agent, of another model
family if available (`review` role in `models.toml`), gets the artifact, the
fixed rubric and the evidence commands, but not the list of fixes or the old
scores. Its score is the result.

## 5. Stop

Stop when either holds:

- every criterion is 10 by the blind re-score;
- for each remaining point, the price is named (time, complexity, a trade-off
  against another criterion) and the user decided it is not worth it.

Any edit after the blind re-score, however small, voids it: re-score again.
Repeat 3–4 otherwise. Three rounds without movement on a criterion means the
problem is structural: say so and propose the larger change.

## Report

The rubric, the first score, the final blind score, per-criterion movement, the
fixes, and the price of each point left on the table.
