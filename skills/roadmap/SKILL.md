---
name: roadmap
description: Use for work too big for one session or with no clear path yet. Maps the decisions as tracker tickets; plans only, never builds.
---

# Roadmap

For an effort whose path is not visible yet. The output is decisions, not code.
When the way is clear, hand over to [to-spec](../to-spec/SKILL.md).

## Chart

1. **Destination.** Settle with the user ([grill-me](../grill-me/SKILL.md)) what
   reaching the end looks like (spec, decision, completed migration) to fix scope.
2. **Frontier.** Interview breadth-first for open decisions and first steps. If
   nothing is foggy and it fits one session, say so and skip the map.
3. **Map.** One tracker item (`docs/agents/issue-tracker.md`):
   - Destination, in two lines.
   - Notes: domain, skills every session should load, standing preferences.
   - Decisions so far: one line per closed ticket, linking it.
   - Not yet specified: the fog, questions you can sense but not yet state.
   - Out of scope: ruled beyond the destination; it never comes back.
4. **Tickets**, as children of the map (one question each, one session, native
   blocking links; stateable questions become tickets even when blocked,
   unstateable stay in fog). Types: **research** ([research](../research/SKILL.md)),
   **prototype** ([prototype](../prototype/SKILL.md)), **grilling** (with user,
   [grill-me](../grill-me/SKILL.md)), **task** (prerequisite, e.g. access).
5. Start the research tickets in background agents. Charting ends here.

## Work the map

One ticket per session (research tickets excepted).

1. Load the map, not every ticket.
2. Take the named ticket, else the first unblocked, unclaimed one; claim it on
   the tracker before starting (other sessions may claim from the map in parallel).
3. Resolve it with its skill; never answer a grilling ticket for the user.
4. Comment the answer, close the ticket, and add one line to Decisions so far.
5. Turn newly clear fog into tickets; close tickets now past destination under Out of scope.

Never write bare ticket numbers: link each ticket with its title or gist (see
[status](../status/SKILL.md#report)).
