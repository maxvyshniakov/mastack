# Publishing

## Branches
- One branch, `main`. Push directly; there is no promote tool.

## Gate
- `.githooks/pre-push` runs `bin/check` on the tree and refuses the push on any
  finding. Enable it once per clone: `git config core.hooksPath .githooks`.
- Before the repository goes public, also run `bin/check --history`.

## Push
- `git push origin <sha>:refs/heads/main`.

## CI
- `.github/workflows/check.yml` runs `bin/check` and `bin/check --history` on
  GitHub-hosted macOS for every push to `main` and every pull request, with a
  read-only token and no secrets. Find the run for a SHA with
  `gh run list --commit <sha>`; the push is finished when it is green.
- Keep it that way: no `pull_request_target`, no self-hosted runners, no
  secrets, actions pinned by commit SHA.

## Release
- Versions are tags `vX.Y.Z` on `main` with the matching `## X.Y.Z` section in
  CHANGELOG.md. Move entries from `Unreleased` into the new section, commit
  `chore: release X.Y.Z`, tag it annotated, push the commit and the tag.

## Install, deploy, restart
- Nothing to install: `bin/install` links skills to the checkout, so a
  `git pull` in each clone updates them.
