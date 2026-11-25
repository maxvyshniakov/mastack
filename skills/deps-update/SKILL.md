---
name: deps-update
description: Use when asked to update dependencies, or when a new runtime, framework or toolchain version is out. Also drops workarounds upstream has fixed.
---

# Dependency update

Two passes: forward (update what is pinned) and back (remove what the update
made unnecessary). The second is the point; the first is routine.

## Inventory

Everything versioned: manifests, lockfiles, runtime (`engines`, version files,
CI setup), SHA-pinned CI actions, container images, toolchains, generators — plus
every workaround:

- `UPSTREAM(...)` marks (`CONTRACT.md`) and pins with reasons in `docs/agents/checks.md`;
- patches (`patches/`, patch-package, vendored forks), shims, polyfills,
  `!important` and other dependency overrides;
- local code reimplementing what a dependency may now provide.

## Forward

- Read the changelog of every intermediate minor and major between old and new
  versions, noting breaking changes, deprecations, and fixes touching our workarounds.
- Update in independently failing groups: runtime, build/test tooling, runtime
  libraries, CI.
- Keep any pin backed by a recorded incident until that incident is re-checked
  on the new version ("it was long ago" is not a check).
- Follow the project's range convention (exact, caret) over the tool's default.

## Back

Check each workaround's upstream issue or release against the new version:

- **Fixed upstream**: remove the workaround, with a regression test if a seam exists.
- **Still open**: keep it and update the mark's condition if it changed.
- **No link**: find one, or mark it as ours with a reason.

## Verify

Run the full gate once ([tdd](../tdd/SKILL.md#checks)). For a published package
others consume, run a pre-publish smoke install from a packed tarball (`npm pack`
into a consumer fixture; post-publish registry install checks belong to
[release](../release/SKILL.md#publish)). Never weaken a check to make an update
pass; hold back an update that needs that with a reason.

## Report

Three lists: **updated** (from → to, notable changes), **removed** (workaround,
why unneeded, evidence), **kept** (workaround or pin, what it waits for). Then
anything held back and why.
