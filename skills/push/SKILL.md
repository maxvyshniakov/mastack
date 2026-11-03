---
name: push
description: Use only for an explicit request to push. Publishes the way docs/agents/publishing.md says and follows CI to a result. Commit-only and skill-authoring requests are not push requests.
---

# Push

A bare request publishes every local commit ahead of the destination on the
current branch, earlier tasks' commits included, without asking about each.
Honor an explicit narrower scope.

## Read the contract

`docs/agents/publishing.md` names the gate, the destination branches, the push
command, CI and the report. If it is missing, say so, publish only to the
current branch's configured upstream by explicit SHA, and ask before anything
else (a release branch, a deploy, CI you cannot see). Never guess a destination.

## Prepare

1. Run the `commit` skill first if task work is still uncommitted.
2. Fetch. Rebase onto the destination if it moved. List the outgoing range
   (`git log --oneline <dest>..<sha>`) and read it.
3. A commit in that range you did not make, bound for a release branch, needs
   its owner's go-ahead.
4. If a pre-push hook runs the gate, do not run the gate by hand first; it would
   run twice. Never pass `--no-verify`; that is the user's call.

## Publish

- Push one SHA with an explicit refspec. If the contract names a promote tool,
  use it and never a bare `git push`: the tool also moves the local branches and
  takes the landing lock; a bare push leaves local branches behind the remote.
- The release branch only when the request uses a word the contract lists for
  it (for example "ship"); a bare "push" goes to the everyday branch. It only
  receives a SHA that the everyday branch receives in the same push, so the
  release branch stays an ancestor of the everyday one.
- Chain dependent steps with `&&` and address other checkouts with `git -C`.
  A `;` once ran a deploy after the push before it was refused.
- Rejected: fetch, read what landed, rebase, push again. Never force.
- Confirm with `git ls-remote`. If more commits arrived, check yours are ancestors.

## CI

Follow every workflow the contract lists to a final result on the pushed SHA.
A run queued for minutes with no runner means the runner is offline; say so.
On failure read the failed log, name the step, fix it in a new commit. A
failure on one OS only is still a failure. Never skip or relax a check to go
green. Rerun only an infrastructure failure, such as a download timeout.

## Report

Branches, range and SHA, whether local branches moved, CI run links and results,
anything after publish (install, deploy), and what was not verified.
