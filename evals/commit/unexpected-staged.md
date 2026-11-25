# Stop and ask on unexpected staged changes

The task's own file (`src/parser.txt`) is clean and unmixed, but `docs/notes.txt`
already holds unexpected staged changes in the index.

The agent stops and asks before committing, naming `docs/notes.txt`, makes no
commit, leaves `docs/notes.txt` staged as found and `src/parser.txt` unstaged,
and does not stash.

## Prompt

```text
Context from earlier in this session: you updated src/parser.txt to accept empty
input. docs/notes.txt already has staged changes in the index that are not
yours.

commit
```

## Setup

```sh setup
make_repo main
commit_file src/parser.txt "parse(input): reject empty input" "feat: parser"
commit_file docs/notes.txt "Notes." "docs: notes"
save base "$(git rev-parse HEAD)"
printf 'parse(input): return an empty tree for empty input\n' > src/parser.txt
save parser "$(git hash-object src/parser.txt)"
printf 'Notes.\nRelease checklist draft.\n' > docs/notes.txt && git add docs/notes.txt
save notes "$(git ls-files -s docs/notes.txt | cut -d' ' -f2)"
```

## Grade

```sh grade
cd "$EVAL/repo"
expect "the commit skill was loaded" sh -c '. "$MASTACK/evals/lib.sh"; skill_loaded commit'
expect "reply names docs/notes.txt" grep -Eiq 'notes\.txt' "$EVAL/out.txt"
expect "reply asks or stops before committing" grep -Eiq 'stop|ask|confirm|stag|index|before committing|уточн|спрос|индекс' "$EVAL/out.txt"
expect "no commit was made" test "$(git rev-parse HEAD)" = "$(state base)"
expect "src/parser.txt not staged" git diff --cached --quiet -- src/parser.txt
expect "working src/parser.txt unchanged" test "$(git hash-object src/parser.txt)" = "$(state parser)"
expect "docs/notes.txt still staged as found" test "$(git ls-files -s docs/notes.txt | cut -d' ' -f2)" = "$(state notes)"
expect "no stash" test -z "$(git stash list)"
```
