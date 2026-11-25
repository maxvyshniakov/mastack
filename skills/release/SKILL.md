---
name: release
description: Use when asked to release, cut a version or publish a package to a registry. Follows docs/agents/publishing.md.
---

# Release

Read the release section of `docs/agents/publishing.md`: how to cut a version,
which branch ships it, how to publish, and which downstream steps follow. If it
is missing, say so and stop; do not invent a release flow.

## Cut late

Other sessions release from the same repository. Cutting a version early collides:
two branches cut the same number and rebase hides it as a changelog conflict.

1. Keep changelog entries under `## Unreleased` until ready to ship.
2. Fetch and rebase onto the release branch.
3. On a changelog conflict, place your entries under `Unreleased` above the
   newest release. Never edit a released section.
4. Decide from the facts before running anything: level (`patch`, `minor`,
   `major`), any `Breaking` entry, first publication, or visibility/access/Pages
   changes.
   - **Standing permission** (`release_standing` in `docs/agents/hooks.json`,
     patch/minor only): once the release gate passed on the commit and every
     review is resolved, cut, push, and publish using the plain doc commands
     alone from the repository root (`bun run release -- <package>:<level>`,
     `bun run release:publish`, `gh workflow run release-npm.yml --ref main`,
     `lanefather promote <sha> --ship`); `bash_guard` passes only those, verified
     against the commit and remote.
   - **Everything else** (major, breaking change, first publication,
     visibility/access/Pages change, or no standing permission): stop with the
     release ready and ask the owner in every harness. Run only after explicit
     approval; a guard permission card is what they approve, not a substitute for
     asking. `MASTACK_RELEASE_OK=<package>@<version>` is owner-set in the
     environment only — never put it in a command.
   - A refusal names the missing fact: fix the fact (fetch, commit, run from root,
     use the plain command) or stop and ask; never respell a command to bypass it.
5. Push refused because a peer landed during the gate: drop your release commit,
   rebase, move your entries back under `Unreleased`, and cut again.

Registry versions are immutable. If someone else published a number, take the next
one; never republish.

## Publish

- From a clean detached worktree or clone at the pushed release commit SHA: local
  WIP or untracked files in a working checkout must never reach the registry.
- After CI on that commit is green, unless the publish command waits itself.
- Verify by installing from the registry, not a local tarball; a registry can
  rewrite package metadata.
- If tagging fails after the package is out, the release exists: repair only the
  tag. Do not change account or Git settings to get past it.

## Downstream

Run downstream dependency upgrades through the project's tool only with explicit
owner approval or standing permission in `publishing.md`. If a downstream check
fails, stop and ask; do not patch the dependent project on your own.

## Report

Version, tag, release commit, registry check, CI result, downstream requests and
their state, and anything not verified.
