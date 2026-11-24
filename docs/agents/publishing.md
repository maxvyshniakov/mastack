# Publishing

## Branches
- Single main branch: `main`. Develop on feature/lane branches or directly on `main` after green checks.
- Releases are annotated tags `vX.Y.Z` on `main`.
- Auto-push of green `orchestrate` batches: explicit push only on `main`.

## Gate
- `.githooks/pre-push` runs `bin/check` on the tree and refuses the push on any
  finding. Enable it once per clone: `git config core.hooksPath .githooks`.
- Before publishing a major change, also run `bin/check --history`.

## Push
- `git push origin <sha>:refs/heads/main`.

## CI
- `.github/workflows/check.yml` runs `bin/check` and `bin/check --history` on
  GitHub-hosted Ubuntu for every push to `main` and every pull request, with a
  read-only token and no secrets. Find the run for a SHA with
  `gh run list --commit <sha>`; the push is finished when it is green.
- Keep it that way: no `pull_request_target`, no self-hosted runners, no
  secrets in CI, actions pinned by commit SHA.

## Release
- Cut a release on `main` only after the target commit passes CI: update
  `CHANGELOG.md`, commit `chore: release X.Y.Z`, tag `git tag -a vX.Y.Z -m "vX.Y.Z"`,
  and push the commit and tag with explicit owner approval (`release_guard`).
- GitHub's `protect-main` and `protect-release-tags` rulesets prevent deletion
  and force-pushes on `main` and `v*` tags.

## Install, deploy, restart
- Nothing to install: `bin/install` links skills to the checkout, so a
  `git pull` in each clone updates them.
