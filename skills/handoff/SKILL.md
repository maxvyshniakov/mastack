---
name: handoff
description: Use when asked to hand work to another agent or pause cleanly. Writes a handoff file.
---

# Handoff

## Reach a pause

Finish or back out the current step so the tree sits in a one-sentence state
(tests green or knowingly red, no half-applied edits). Commit or push only if
already asked.

## Write the file

Write to the user's path, else a shared notes folder, else the OS temp directory
(not the repo unless asked), and report the absolute path.

Contents, in this order:

1. **Goal**: what done looks like, in one or two sentences.
2. **State**: repo, branch, `HEAD` SHA, dirty files, running processes, held
   leases, and progress against the goal.
3. **Done**: finished, verified work and how it was verified.
4. **Next**: ordered remaining steps concrete enough to start without rereading
   the conversation.
5. **Decisions**: choices and reasons, especially rejected ideas that would
   otherwise be suggested again.
6. **Open questions**: what waits on the user, each with a recommendation.
7. **Pointers**: paths and URLs to specs, issues, commits, logs, notes (link;
   do not paste artifact contents).
8. **Skills**: skills the next agent should load (`tdd`, `debug`, `push`, etc.).

Redact secrets and personal data. The file may become another agent's prompt.
