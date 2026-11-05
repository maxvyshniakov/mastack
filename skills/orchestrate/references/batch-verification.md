# Batch evidence

## Accepted scope

Keep the batch's accepted requirements in the existing work notes, including
follow-ups. The tracker remains authoritative for issue scope and decisions.
Each row records the requirement/source, owner, status, implementation commit,
verification or blocker, and tracker readback (or not applicable).

Before reporting completion, reconcile every row with the actual changes and
checks. A green gate proves the checked inputs, not that all accepted scope was
implemented. Keep unfinished rows visible alongside completed work.

## Cross-cutting verification

For a migration or legacy removal, use the configured batch gate to collect the
independent results before assigning fixes. Ordinary focused TDD failures stay
in their test loop; they do not require a diagnostic full gate.

Freeze the source, dependency and generated-input identities while checks read
them. Save the candidate, command, run conditions and artifact provenance with
the log. Nested jobs stay within the execution lease's budget.

Record each check's outcome, actual exit status, duration and log. A failed
prerequisite blocks dependent checks with its cause; independent checks keep
running. Distinguish setup and behavior failures, cleanup failures,
interruptions and checks that did not run. An interrupted run is incomplete.

Distribute related failures with their evidence after collecting the ledger.
Confirm the assembled fixes through the project's gate. Reuse a complete green
run whose checked inputs are unchanged; do not repeat it solely because it
collected all results. Selected checks remain selected evidence. Follow the
project's gate/stamp contract and leave prerequisite blockage visible.

## Tracker readback

Record the outcome, commits (identifying local-only candidates), verification,
remaining scope and blockers through the project's tracker policy. Reconcile
acceptance lists, dependencies and the parent map; close only completed scope.
Read back changed bodies, comments, states and dependencies before recording
synchronization as complete. A successful write alone is insufficient, and
local notes do not replace the tracker.
