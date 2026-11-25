---
name: research
description: Use when a decision needs facts from outside the repository. A background agent reads primary sources and writes one cited file.
---

# Research

Hand the reading to a background agent using
`<this skill's directory>/scripts/role research [--harness auto|claude|codex|t3]`,
and keep working while it reads.

The brief names:

- **The question**, and the decision it feeds, so the agent knows what matters.
- **Sources to prefer**: official docs, source code at a pinned version or
  commit, specs, changelogs, first-party APIs, maintainer issue threads. Use
  secondary write-ups only to locate a primary source.
- **Where to write**: the research notes directory in `docs/agents/domain.md`,
  else a scratch or notes folder; never the product tree by accident.

The agent:

1. Follows every claim to its owning source at the version in use here.
2. Runs a small probe when reading cannot settle it (script against the real
   API or library), and says so.
3. Writes one file: answer first, then findings with links (file:line or anchor,
   version), then what stayed unknown.
4. Marks what it inferred, as opposed to read.

Read the file and spot-check load-bearing claims before relying on it.
