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
  GitHub-hosted Ubuntu for every push to `dev` or `main` and every pull request, with a
  read-only token and no secrets. Find the run for a SHA with
  `gh run list --commit <sha>`; the push is finished when it is green.
- Keep it that way: no `pull_request_target`, no self-hosted runners, no
  secrets in CI, actions pinned by commit SHA.

## Release
- After the published dev commit passes CI, run `bin/promote X.Y.Z`. It
  dispatches the promote workflow on main with the exact dev SHA and version.
  Follow the run in Actions. The workflow checks the green dev push and
  ancestry, builds the release commit from Git objects, then pushes the commit
  to both branches and its annotated tag atomically. Fetch and fast-forward
  the local dev checkout, then follow CI on both branches.
- GitHub's `main-promote-only` ruleset restricts updates to main. Only deploy
  keys bypass that rule. Keep exactly one writable deploy key, Mastack Promote.
  Its private half is an environment secret in `promote-main`, restricted to
  the main branch. The ordinary CI workflow uses no secrets. Adding another
  writable deploy key or changing these administrator settings changes who
  can publish. The separate rule against deletion and force-push has no bypass.

## Install, deploy, restart
- Nothing to install: `bin/install` links skills to the checkout, so a
  `git pull` in each clone updates them.
