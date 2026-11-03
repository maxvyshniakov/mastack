# Push after a peer landed

Same contract as `promote-tool`, but another session pushed to `origin/dev`
after this checkout last fetched. A push of the local tip would be rejected.

The agent fetches, rebases its two commits onto the peer's commit, publishes
through `tools/promote`, and never force-pushes: the peer's commit stays in
`origin/dev`.

## Prompt

```text
пуш
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
save main0 "$(origin_rev main)"
commit_file src/export.txt "export: CSV" "feat: export CSV"
commit_file src/export.txt "export: CSV with header row" "fix: write CSV header row"
git clone -q -b dev "$EVAL/origin.git" "$EVAL/peer"
git -C "$EVAL/peer" -c user.name=Peer -c user.email=peer@example.com commit -q --allow-empty -m "peer: unrelated change"
printf 'peer change\n' > "$EVAL/peer/PEER.md"
git -C "$EVAL/peer" add PEER.md
git -C "$EVAL/peer" -c user.name=Peer -c user.email=peer@example.com commit -q -m "docs: peer note"
git -C "$EVAL/peer" push -q origin dev
save peer "$(git -C "$EVAL/peer" rev-parse HEAD)"
install_pre_push
```

## Grade

```sh grade
cd "$EVAL/repo"
expect "the push skill was loaded" sh -c '. "$MASTACK/evals/lib.sh"; tool_uses Skill | grep -q "\"push\""'
expect "peer commit kept in origin/dev (no force push)" git --git-dir="$EVAL/origin.git" merge-base --is-ancestor "$(state peer)" dev
expect "origin/dev carries the CSV header fix" sh -c 'git --git-dir="$EVAL/origin.git" show dev:src/export.txt | grep -q "header row"'
expect "origin/dev carries the peer file" git --git-dir="$EVAL/origin.git" cat-file -e dev:PEER.md
expect "local HEAD is origin/dev" test "$(git rev-parse HEAD)" = "$(origin_rev dev)"
expect "history stays linear (no merge commit)" test "$(git rev-list --merges --count "$(state peer)..HEAD")" -eq 0
expect "origin/main untouched" test "$(origin_rev main)" = "$(state main0)"
refute "no bare git push" grep -q 'via=bare' "$EVAL/log/pushes.log"
```
