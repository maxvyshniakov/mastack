---
name: push
description: Use for an explicit request to push, or when an orchestrator pushes a green batch to the everyday branch. Publishes the way docs/agents/publishing.md says and follows CI to a result. Commit-only and skill-authoring requests are not push requests.
---

# Push

A bare request publishes every local commit ahead of the destination on the
current branch (earlier tasks' commits included) without asking about each.
Honor an explicit narrower scope.

## Read the contract

`docs/agents/publishing.md` names the gate, destination branches, push command,
CI and report. If missing, say so, publish only to the current branch's
configured upstream by explicit SHA, and ask before anything else (release
branch, deploy, unseen CI). Never guess a destination.

## Prepare

1. Run [commit](../commit/SKILL.md) first if task work is still uncommitted.
2. Fetch, rebase onto the destination if it moved, and read the outgoing range
   (`git log --oneline <dest>..<sha>`).
3. Any unowned commit in that range bound for a release branch needs its owner's
   go-ahead.
4. When a pre-push hook runs the gate, do not run it by hand first (it would run
   twice). Never pass `--no-verify`; that is the user's call.

## Publish

- Push one SHA with an explicit refspec. When the contract names a promote tool,
  use it and never bare `git push`: it moves local branches and takes the landing
  lock; bare push leaves local branches behind the remote.
- Push the release branch only on a contract trigger word (e.g. "ship"); bare
  "push" goes to the everyday branch. The release branch only receives a SHA the
  everyday branch receives in the same push, keeping it an ancestor.
- Chain dependent steps with `&&` and address other checkouts with `git -C`
  (`;` once ran a deploy after a refused push).
- Rejected: fetch, read what landed, rebase, push again. Never force.
- Confirm with `git ls-remote`; if newer commits arrived, check yours are ancestors.

## CI

Follow every workflow the contract lists to a final result on the pushed SHA.
A run queued for minutes with no runner means the runner is offline; say so.
On failure read the log, name the step, and fix it in a new commit. A single-OS
failure is still a failure — never treat a local macOS gate pass as Linux CI.
Rerun only infrastructure failures (e.g. download timeout); never skip or relax
a check.

Even on nightly/schedule-only repos (no push-triggered workflow), inspect the
destination's latest completed runs (`gh run list --branch <dest> --limit 5`)
and report any red nightly or automated-update step and root cause.

## Report

Branches, range and SHA, whether local branches moved, CI run links and results,
post-publish steps (install, deploy), and what was not verified.
