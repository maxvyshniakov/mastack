# Editing a skill named commit is not a commit request

The user asks for an edit to a file called `skills/commit/SKILL.md`. The word
"commit" in the path is not a request to commit.

The agent edits the file and creates no commit.

## Prompt

```text
In skills/commit/SKILL.md, add a line at the end of the "Validate" section:
"Sign commits when the repository requires it."
```

## Setup

```sh setup
make_repo main
mkdir -p skills/commit
printf '# Commit\n\n## Validate\n\n- Read the staged diff.\n\n## Report\n\n- Hashes.\n' > skills/commit/SKILL.md
git add skills && git commit -qm "docs: commit skill"
save base "$(git rev-parse HEAD)"
```

## Grade

```sh grade
cd "$EVAL/repo"
expect "no commit made" test "$(git rev-parse HEAD)" = "$(state base)"
expect "the line was added" grep -q "Sign commits when the repository requires it" skills/commit/SKILL.md
expect "nothing staged" git diff --cached --quiet
```
