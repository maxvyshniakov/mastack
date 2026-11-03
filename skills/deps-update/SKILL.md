---
name: deps-update
description: Use when asked to update dependencies, or when a new runtime, framework or toolchain version is out. Also drops workarounds upstream has fixed.
---

# Dependency update

Two passes: forward (update what is pinned) and back (remove what the update
made unnecessary). The second is the point; the first is routine.

## Inventory

Everything with a version: package manifests and lockfiles, the runtime
(engines fields, version files, CI setup steps), CI actions (pinned by SHA),
container images, toolchains, generators. Also the workarounds:

- `UPSTREAM(...)` marks (`CONTRACT.md`) and pins listed with reasons in
  `docs/agents/checks.md`;
- patches (`patches/`, patch-package, vendored forks), shims, polyfills,
  `!important` and other overrides of a dependency's behavior;
- code of ours that reimplements what a dependency may now provide.

## Forward

- Read the changelog of every minor and major between the old and new version,
  not just the latest. Note breaking changes, deprecations, and fixes that touch
  our workarounds.
- Update in groups that fail independently: runtime, build and test tooling,
  runtime libraries, CI.
- A pin with a recorded incident behind it stays until the incident is
  re-checked on the new version. "It was long ago" is not a check.
- Prefer the project's own range convention (exact, caret) over the tool's
  default.

## Back

For each workaround: find the upstream issue or release that it waits for, and
check its state against the new version. Then:

- **Fixed upstream**: remove the workaround, with a test that fails if the
  original bug returns, if the project has a seam for it.
- **Still open**: keep it, update the mark's condition if it changed.
- **No link**: find one, or mark it as ours with a reason.

## Verify

Run the full gate once on the result. For a package others consume, also
install it the way consumers do, from the registry or a packed tarball, since a
registry can rewrite metadata. Never weaken a check to make an update pass;
an update that needs that is held back with a reason.

## Report

Three lists: **updated** (from → to, notable changes), **removed** (workaround,
why it is no longer needed, evidence), **kept** (workaround or pin, what it
waits for). Then anything held back and why.
