# Batch evidence

## Accepted scope

Keep the batch's accepted requirements in the existing work notes, including
follow-ups. The tracker remains authoritative for issue scope and decisions.
Each row records requirement/source, owner, status, implementation commit,
verification or blocker, and tracker readback (or not applicable).

Before reporting completion, reconcile every row with actual changes and checks.
A green gate proves checked inputs, not that all accepted scope was implemented.
Keep unfinished rows visible alongside completed work.

## Cross-cutting verification

For a migration or legacy removal, run the configured batch gate to collect all
independent results before assigning fixes. Ordinary focused TDD failures stay
in their test loop without a diagnostic full gate.

Freeze source, dependency, and generated-input identities while checks read
them; record candidate, command, run conditions, and provenance with the log.
Nested jobs stay within the execution lease's budget.

Record each check's outcome, exit status, duration, and log. A failed
prerequisite blocks dependent checks with its cause while independent checks
continue; distinguish setup/behavior failures, cleanup failures, interruptions
(incomplete), and unrun checks. Distribute related failures with evidence, then
confirm assembled fixes through the project's gate/stamp contract. Reuse a
complete green run whose checked inputs are unchanged rather than rerunning it
solely because it collected all results, keeping prerequisite blockage visible.

## Tracker readback

Record outcome, commits (identifying local-only candidates), verification,
remaining scope, and blockers per the project's tracker policy. Reconcile
acceptance lists, dependencies, and the parent map; close only completed scope.
Read back changed bodies, comments, states, and dependencies before marking
synchronization complete — a successful write alone is insufficient, and local
notes do not replace the tracker.
