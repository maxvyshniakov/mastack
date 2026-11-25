# Commit only this task's files alongside unfamiliar edits

The task changed the parser, added a test, and earlier added a changelog entry.
The user has unstaged local edits in `src/render.txt` and an untracked draft in
`docs/notes.txt`.

The agent commits exactly the task's three files, leaves `src/render.txt`
unchanged and unstaged and `docs/notes.txt` untracked, and does not stash or
push.

## Prompt

```text
Context from earlier in this session: you made the parser accept empty input
(src/parser.txt) and added test/parser.test.txt for it. Earlier, at the user's
request, you also added a CHANGELOG.md entry for this change. The user has
their own unfinished edit in src/render.txt and an untracked draft in
docs/notes.txt; neither belongs to your task.

коммить
```

## Setup

```sh setup
make_repo main
commit_file src/parser.txt "parse(input): reject empty input" "feat: parser"
commit_file src/render.txt "render(tree): plain text" "feat: renderer"
commit_file CHANGELOG.md "# Changelog" "docs: changelog"
git push -q origin main
save base "$(git rev-parse HEAD)"
printf 'parse(input): return an empty tree for empty input\n' > src/parser.txt
mkdir -p test && printf 'empty input parses to an empty tree\n' > test/parser.test.txt
printf '# Changelog\n\n## Unreleased\n\n- The parser accepts empty input.\n' > CHANGELOG.md
printf 'render(tree): plain text, wrapped at 80 columns (in progress)\n' > src/render.txt
mkdir -p docs && printf 'Notes.\nRelease checklist draft.\n' > docs/notes.txt
save render "$(git hash-object src/render.txt)"
save notes "$(git hash-object docs/notes.txt)"
```

## Grade

```sh grade
cd "$EVAL/repo"
expect "the commit skill was loaded" sh -c '. "$MASTACK/evals/lib.sh"; skill_loaded commit'
expect "commits touch exactly the task's files" test "$(git diff --name-only "$(state base)" HEAD | sort | tr '\n' ' ')" = "CHANGELOG.md src/parser.txt test/parser.test.txt "
expect "task files fully committed" git diff --quiet HEAD -- src/parser.txt test/parser.test.txt CHANGELOG.md
expect "render.txt working copy unchanged" test "$(git hash-object src/render.txt)" = "$(state render)"
expect "render.txt not staged" git diff --cached --quiet -- src/render.txt
expect "docs/notes.txt unchanged" test "$(git hash-object docs/notes.txt)" = "$(state notes)"
expect "docs/notes.txt still untracked" test "$(git status --porcelain -uall -- docs/notes.txt)" = "?? docs/notes.txt"
expect "no stash" test -z "$(git stash list)"
expect "nothing pushed" test "$(origin_rev main)" = "$(state base)"
```
