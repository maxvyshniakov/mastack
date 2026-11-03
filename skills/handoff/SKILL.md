---
name: handoff
description: Use when asked to hand work to another agent or pause cleanly, or when context runs low mid-task. Writes a handoff file.
---

# Handoff

## Reach a pause

Finish the step in progress, or back out of it, so the tree is in a state you
can describe in one sentence: tests green or knowingly red, no half-applied
edits. Do not commit or push unless that was already asked for.

## Write the file

Where: the path the user gives, else a shared notes folder for this work, else
the OS temp directory. Not the repository, unless asked. Report the absolute path.

Contents, in this order:

1. **Goal**: what done looks like, in one or two sentences.
2. **State**: repository, branch, `HEAD` SHA, dirty files, running processes
   and held leases, where the tree stands against the goal.
3. **Done**: what is finished and verified, and how it was verified.
4. **Next**: the remaining steps, in order, concrete enough to start without
   rereading the conversation.
5. **Decisions**: what was decided and why, especially what was rejected and
   would otherwise be suggested again.
6. **Open questions**: what waits on the user, each with a recommended answer.
7. **Pointers**: paths and URLs to specs, issues, commits, logs, notes. Link;
   do not paste what an artifact already holds.
8. **Skills**: which skills the next agent should load, such as `tdd`, `debug`
   or `push`.

Redact secrets and personal data. The file may become another agent's prompt.

## Continue, compact, delegate or hand off

At a phase boundary, pick the cheapest option that keeps what matters:

- **Continue** when the next phase needs what is in context and it still fits.
- **Subagent** for a narrow side task whose result is a short report.
- **Compact** when the next phase needs the gist but not the detail.
- **Handoff** when the work moves to a new session, harness, directory or person,
  or when a side task forks off mid-phase.
