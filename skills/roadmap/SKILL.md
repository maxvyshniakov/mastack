---
name: roadmap
description: Use for work too big for one session or with no clear path yet. Maps the decisions as tracker tickets; plans only, never builds.
---

# Roadmap

For an effort whose path is not visible yet. The output is decisions, not code.
When the way is clear, hand over to `to-spec`.

## Chart

1. **Destination.** Settle with the user (`grill-me`) what reaching the end
   looks like: a spec, a decision, a migration done. It fixes the scope.
2. **Frontier.** Interview breadth-first across the whole space for the open
   decisions and the first steps that can be taken now. If nothing is foggy and
   it fits one session, say so and skip the map.
3. **Map.** One tracker item (`docs/agents/issue-tracker.md`):
   - Destination, in two lines.
   - Notes: domain, skills every session should load, standing preferences.
   - Decisions so far: one line per closed ticket, linking it.
   - Not yet specified: the fog, questions you can sense but not yet state.
   - Out of scope: ruled beyond the destination; it never comes back.
4. **Tickets**, as children of the map, one question each, sized for one
   session, with native blocking links. A question you can state precisely is a
   ticket even when blocked; one you cannot yet state stays in the fog.
   Types: **research** (agent alone, `research` skill), **prototype** (with the
   user, `prototype`), **grilling** (with the user, `grill-me`), **task** (work
   that must happen before a decision, such as getting access).
5. Start the research tickets in background agents. Charting ends here.

## Work the map

One ticket per session (research tickets excepted).

1. Load the map, not every ticket.
2. Take the ticket the user names, else the first unblocked, unclaimed one.
   Claim it before working.
3. Resolve it with its skill. A grilling ticket needs the user; never answer for
   them.
4. Record the answer as a comment, close the ticket, add one line to
   Decisions so far.
5. Turn fog the answer made clear into new tickets; move tickets that now fall
   past the destination to Out of scope, closed.

Refer to tickets by title in everything the user reads, with the link inside
the title. Other sessions may work the same map in parallel.
