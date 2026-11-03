---
name: research
description: Delegate a factual question to a background agent that reads primary sources only and writes one cited Markdown file. Use for "research", "выясни", "почитай доки", "how does library X do Y", or a decision waiting on facts from outside the repository.
---

# Research

Hand the reading to a background agent, with the `research` role's model from
`models.toml`, and keep working while it reads.

The brief names:

- **The question**, and the decision it feeds, so the agent knows what matters.
- **Sources to prefer**: official documentation, source code at a pinned
  version or commit, specifications, changelogs, first-party APIs, issue
  threads by maintainers. Secondary write-ups only to find a primary source.
- **Where to write**: where the repository keeps such notes, else a scratch or
  notes folder; never the product tree by accident.

The agent:

1. Follows every claim to the source that owns it, at the version in use here.
2. Runs a small probe when reading cannot settle it (a script against the real
   API or library), and says so.
3. Writes one file: the answer first, then each finding with its link (file and
   line or anchor, version), then what stayed unknown.
4. Marks what it inferred, as opposed to read.

When it reports, read the file before relying on it. Spot-check the claims the
decision rests on.
