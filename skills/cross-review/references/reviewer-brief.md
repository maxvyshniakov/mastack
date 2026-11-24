# Reviewer brief

What every reviewer is asked for on top of its pass. The reviewer has already
paid for reading the diff, the code around it and the engine under it; these
questions cost output only (10–20% in the runs that set them) and return what
the orchestrator would otherwise rebuild by rereading the same code.

Tell the reviewer to finish Part 1 before starting Part 2: asked together, the
wider questions dilute the defect hunt.

## Part 1: each finding

A stable id (`F1`, `F2`, …), severity, file and line, what is wrong, a concrete
scenario (inputs → wrong result), how it was verified, and:

- **Confidence and falsifier.** High, medium or low; the one cheapest check
  that would confirm or kill the finding (a unit test in a sentence, one
  measurement in a browser); and what the claim rests on that the reviewer
  could not see (effect order, engine or browser behaviour). A finding that
  hinged on effect order arrived as a flat P1 and cost a second read of the
  code to learn that.
- **Should have been caught by.** The existing test that ought to fail and why
  it does not, else the cheapest new guard: unit test, browser check, lint
  rule or source-scan test.
- **Fix direction.** The layer to fix it in and the layer not to, the size
  ("about N lines" or "a lane"), and whether consumers will see the fix. No
  fix code: the reviewer patches the symptom where it saw it, and the
  implementer anchors on the patch.

Then what was examined and found sound, and what was not examined.

## Part 2: wider than the diff

At most five items, ids `W1`…; "nothing" is a full answer. From what the
reviewer already read, plus one repository-wide grep per item. Each is a lead,
marked unverified unless verified, with a size: small (about N lines, one
sensible outcome), a lane, or owner's decision.

1. **Class.** A finding that is one instance of a repeating pattern: the grep
   pattern, the number of hits, two or three examples, and the mechanism that
   would close the whole class (lint rule, source-scan test, shared helper).
2. **Symmetry.** What the change tidied in one place while the same thing
   stays untidied beside it.
3. **Wrong level.** A patch over something that belongs in another layer, a
   production change made for a tooling problem, two ways to do one thing.
4. **Unasked.** A decision taken silently, a contract written nowhere, a
   consumer-visible change nobody named.

An item sized "owner's decision" comes as the question itself: one sentence of
context, two or three options, what each changes or breaks, and the
recommended one with its reason.

## Part 3: triage

- **Roots.** The ids that grow from one cause, with the cause in a line.
- **Top three.** The ids to fix if only three get fixed, in order.
- **Table.** One row per id: id | severity or "lead" | file | root |
  confidence | falsifier | size | consumer-visible. Reports from two reviewers
  are compared and deduplicated by this table.

The reply ends with the counts by severity, the top three, and the share of
effort Parts 2 and 3 took.
