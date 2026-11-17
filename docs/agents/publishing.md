# Publishing

## Branches
- Develop on `dev`. Every promotion to `main` is a tagged release.

## Gate
- `.githooks/pre-push` runs `bin/check` on the tree and refuses the push on any
  finding. Enable it once per clone: `git config core.hooksPath .githooks`.
- Before the repository goes public, also run `bin/check --history`.

## Push
- `git push origin <sha>:refs/heads/dev`.

## CI
- `.github/workflows/check.yml` runs `bin/check` and `bin/check --history` on
  GitHub-hosted macOS for every push to `dev` or `main` and every pull request, with a
  read-only token and no secrets. Find the run for a SHA with
  `gh run list --commit <sha>`; the push is finished when it is green.
- Keep it that way: no `pull_request_target`, no self-hosted runners, no
  secrets, actions pinned by commit SHA.

## Release
- On a request to promote or release, push the intended work to `dev` and wait
  for green CI. Run `bin/promote X.Y.Z` from the repository. It clones
  published `dev`, moves the Unreleased notes under the version, commits,
  and atomically pushes the checked commit to both branches with its annotated
  tag. If dev advances concurrently, inspect the new changes before retrying.
- Fetch and fast-forward the local dev checkout after promotion. Follow CI
  for both branches on the release SHA.

## Install, deploy, restart
- Nothing to install: `bin/install` links skills to the checkout, so a
  `git pull` in each clone updates them.
