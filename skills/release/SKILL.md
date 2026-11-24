---
name: release
description: Use when asked to release, cut a version or publish a package to a registry. Follows docs/agents/publishing.md.
---

# Release

Read the release section of `docs/agents/publishing.md`: how to cut a version,
which branch ships it, how to publish, and which downstream steps follow. If it
is missing, say so and stop; do not invent a release flow.

## Cut late

Other sessions release from the same repository. A version cut early collides:
two branches each cut the same number, and the rebase hides it as a changelog
conflict.

1. Keep changelog entries under `## Unreleased` until the work is ready to ship.
2. Fetch and rebase onto the release branch.
3. On a changelog conflict, put your entries under `Unreleased` above the newest
   release. Never edit a released section.
4. Decide from the facts first, before running anything: the level (patch,
   minor, major), whether the CHANGELOG has a Breaking entry, whether it is the
   package's first publication, and whether anything changes visibility,
   access or Pages.
   - A patch or minor of a package the project's publishing doc gives a
     standing permission for (`release_standing` in `docs/agents/hooks.json`):
     once the release gate passed on the commit and every review is resolved,
     cut, push and publish it yourself, with the plain commands of that doc
     (`bun run release -- <package>:<level>`, `bun run release:publish`,
     `gh workflow run release-npm.yml --ref main`, `lanefather promote <sha>
     --ship`), each alone and from the repository root: `bash_guard` passes
     only those, checked against the commit and the remote.
   - Anything else (a major, a breaking change, a first publication, a
     visibility, access or Pages change, a project without the standing
     permission): stop with the release ready and ask the owner, in every
     harness. Run the command only after he tells you to; where the guard then
     shows a permission card, that card is what he approves, not a substitute
     for asking him. `MASTACK_RELEASE_OK=<package>@<version>` in the
     environment also grants it, but only the owner sets it: never put
     `MASTACK_RELEASE_OK` in a command.
   - A refusal names the missing fact: fix the fact (fetch, commit, run from
     the root, use the plain command) or stop and ask; never respell the
     command to get past it.
5. Push refused because a peer landed during the gate: drop your release commit,
   rebase, move your entries back under `Unreleased`, cut again.

Registry versions are immutable. If a number was published by someone else,
take the next one; never republish.

## Publish

- From a clean checkout whose `HEAD` is the pushed release commit by SHA: a fresh
  detached worktree or clone. The shared tree may hold someone's edits, and a
  dirty tree must not reach the registry.
- After CI on that commit is green, unless the publish command waits itself.
- Check the result by installing from the registry, not from a local tarball;
  a registry can rewrite package metadata.
- If tagging fails after the package is out, the release exists: repair only the
  tag. Do not change account or Git settings to get past it.

## Downstream

When a release triggers upgrades in dependent projects, run them through the
project's tool and only with the owner's explicit approval, or a standing one
written in `publishing.md`. If a downstream check fails, stop and ask; do not
patch the dependent project on your own.

## Report

Version, tag, release commit, registry check, CI result, downstream requests
and their state, and anything not verified.
