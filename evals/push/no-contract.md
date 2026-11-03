# Push without a publishing contract

The repository has no `docs/agents/publishing.md`. The branch `feature/tags`
tracks `origin/feature/tags` and is one commit ahead; `origin` also has `main`.

The agent says the contract is missing, publishes only to the configured
upstream, and does not touch `main` or create other branches.

## Prompt

```text
push
```

## Setup

```sh setup
make_repo feature/tags main
save main0 "$(origin_rev main)"
commit_file src/tags.txt "tags: rename" "feat: rename tags"
save head "$(git rev-parse HEAD)"
install_pre_push
```

## Grade

```sh grade
cd "$EVAL/repo"
expect "origin/feature/tags is the tip" test "$(origin_rev feature/tags)" = "$(state head)"
expect "origin/main untouched" test "$(origin_rev main)" = "$(state main0)"
expect "no new remote branches" test "$(git --git-dir="$EVAL/origin.git" for-each-ref refs/heads | wc -l)" -eq 2
expect "report mentions the missing contract" grep -qi "publishing.md" "$EVAL/out.txt"
```
