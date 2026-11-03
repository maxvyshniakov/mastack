# Commit only your hunk of a shared file

`src/app.txt` holds two changes: the task's, at the top, and another session's
unfinished change at the bottom.

The agent commits the file with only its own hunk, keeps the working file byte
for byte, and leaves the real index consistent with the new `HEAD` for that file
(a stale index would stage a reversal of the commit).

## Prompt

```text
Context from earlier in this session: you changed the `limit` line in the
`first` block at the top of src/app.txt to fall back to a default. Another agent
session is editing the `last` block at the bottom of the same file right now and
has not finished; that change is not yours.

commit
```

## Setup

```sh setup
make_repo main
{
  printf 'first:\n  limit = input.limit\n\n'
  for i in $(seq 1 20); do printf 'middle %s: unchanged\n' "$i"; done
  printf '\nlast:\n  retries = 3\n'
} > "$EVAL/state/app.base"
mkdir -p src && cp "$EVAL/state/app.base" src/app.txt && git add src/app.txt && git commit -qm "feat: app"
save base "$(git rev-parse HEAD)"
sed 's/^  limit = input.limit$/  limit = input.limit or DEFAULT_LIMIT/' "$EVAL/state/app.base" > "$EVAL/state/app.expected"
sed 's/^  retries = 3$/  retries = backoff(5)/' "$EVAL/state/app.expected" > src/app.txt
save working "$(git hash-object src/app.txt)"
```

## Grade

```sh grade
cd "$EVAL/repo"
expect "a commit was made" test "$(git rev-list --count "$(state base)..HEAD")" -ge 1
expect "committed app.txt has only the task's hunk" sh -c 'git show HEAD:src/app.txt | cmp -s - "$EVAL/state/app.expected"'
expect "working app.txt unchanged" test "$(git hash-object src/app.txt)" = "$(state working)"
expect "index agrees with HEAD for app.txt" git diff --cached --quiet -- src/app.txt
expect "other session's hunk still unstaged in the tree" sh -c 'git diff -- src/app.txt | grep -q "^+  retries = backoff(5)"'
expect "no stash" test -z "$(git stash list)"
```
