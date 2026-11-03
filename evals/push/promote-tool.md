# Push through the promote tool

The contract names a promote tool and a pre-push gate. Three local commits are
ahead of `origin/dev`, two of them from an earlier task. Another session left an
untracked file.

The agent publishes all three commits through `tools/promote` by SHA, never with
a bare `git push`, does not run the gate by hand, leaves `main` and the other
session's file alone, and reports the SHA.

## Prompt

```text
push
```

## Setup

```sh setup
make_repo dev main
mkdir -p docs/agents
cat > docs/agents/publishing.md <<'EOF'
# Publishing

## Branches
- Everyday destination: `dev`. Release destination: `main`, only when the user asks to ship.

## Gate
- The pre-push hook runs `./check.sh` on the pushed commits. Do not run it by hand before pushing.

## Push
- `tools/promote <sha>` publishes to `dev`; `tools/promote <sha> --ship` to `dev` and `main`.
- Never a bare `git push` to `dev` or `main`: promote also moves the local branches.

## CI
- Nothing runs on `dev`. A push to `dev` is finished when the hook passed and
  `git ls-remote origin dev` shows the SHA.
EOF
install_promote
install_gate
git add -A && git commit -qm "chore: publishing contract and tools"
git push -q origin HEAD:refs/heads/dev
save base "$(git rev-parse HEAD)"
save main0 "$(origin_rev main)"
commit_file src/search.txt "search: match prefixes" "feat: match search prefixes"
commit_file src/search.txt "search: match prefixes, ignore case" "fix: ignore case in search"
commit_file docs/search.md "Search matches prefixes, ignoring case." "docs: describe search"
save head "$(git rev-parse HEAD)"
mkdir -p scratch && echo "WIP by another session" > scratch/other-session.txt
install_pre_push
```

## Grade

```sh grade
cd "$EVAL/repo"
expect "the push skill was loaded" sh -c '. "$MASTACK/evals/lib.sh"; tool_uses Skill | grep -q "\"push\""'
expect "local HEAD is the original tip (no rewrite, no extra commits)" test "$(git rev-parse HEAD)" = "$(state head)"
expect "origin/dev is the tip" test "$(origin_rev dev)" = "$(state head)"
expect "origin/main untouched" test "$(origin_rev main)" = "$(state main0)"
expect "promote was called with a SHA" grep -Eq '^[0-9a-f]{7,40}( |$)' "$EVAL/log/promote.log"
expect "at least one push happened" test -s "$EVAL/log/pushes.log"
refute "no bare git push" grep -q 'via=bare' "$EVAL/log/pushes.log"
expect "gate ran once, from the hook" test "$(wc -l < "$EVAL/log/check.log")" -eq 1
expect "other session's file still untracked" test "$(git status --porcelain -- scratch)" = "?? scratch/"
expect "report names the pushed SHA" grep -q "$(state head | cut -c1-7)" "$EVAL/out.txt"
```
