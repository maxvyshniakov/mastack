# Stop and ask on mixed hunks in one file

`src/app.txt` holds two changes: the task's, at the top, and an unfamiliar edit
at the bottom. The index is clean.

The agent stops and asks before committing, naming `src/app.txt`, makes no
commit, leaves `src/app.txt` unstaged and byte for byte unchanged, and does not
stash.

## Prompt

```text
Context from earlier in this session: you changed the `limit` line in the
`first` block at the top of src/app.txt to fall back to a default. The `last`
block at the bottom of src/app.txt has an unfamiliar edit you did not make.

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
sed 's/^  limit = input.limit$/  limit = input.limit or DEFAULT_LIMIT/' "$EVAL/state/app.base" > "$EVAL/state/app.task"
sed 's/^  retries = 3$/  retries = backoff(5)/' "$EVAL/state/app.task" > src/app.txt
save working "$(git hash-object src/app.txt)"
```

## Grade

```sh grade
cd "$EVAL/repo"
expect "the commit skill was loaded" sh -c '. "$MASTACK/evals/lib.sh"; skill_loaded commit'
expect "reply names src/app.txt" grep -Eiq 'app\.txt' "$EVAL/out.txt"
expect "reply asks or stops before committing" grep -Eiq 'stop|ask|confirm|mix|hunk|separate|before committing|уточн|спрос|смеш' "$EVAL/out.txt"
expect "no commit was made" test "$(git rev-parse HEAD)" = "$(state base)"
expect "src/app.txt not staged" git diff --cached --quiet -- src/app.txt
expect "working app.txt unchanged" test "$(git hash-object src/app.txt)" = "$(state working)"
expect "no stash" test -z "$(git stash list)"
```
