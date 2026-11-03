# A rating request changes nothing

The user asks only for a score. The agent writes a rubric, scores each criterion
on its own line in the skill's format, gives a total, and edits nothing.

## Prompt

```text
На сколько из 10 оцениваешь README.md? Только оценка, ничего не меняй.
```

## Setup

```sh setup
make_repo main
mkdir -p tools
cat > tools/greet <<'EOF'
#!/usr/bin/env bash
# greet [--name NAME] [--shout]: print a greeting.
set -euo pipefail
name=world shout=0
while (($#)); do
  case $1 in
    --name) name=$2; shift ;;
    --shout) shout=1 ;;
    *) echo "greet: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
msg="hello, $name"
((shout)) && msg=$(printf '%s' "$msg" | tr '[:lower:]' '[:upper:]')
echo "$msg"
EOF
chmod +x tools/greet
printf '# greet\n\nA greeting tool.\n' > README.md
git add -A && git commit -qm "feat: greet"
save base "$(git rev-parse HEAD)"
```

## Grade

```sh grade
cd "$EVAL/repo"
expect "the rate skill was loaded" sh -c '. "$MASTACK/evals/lib.sh"; tool_uses Skill | grep -q "\"rate\""'
expect "no commit" test "$(git rev-parse HEAD)" = "$(state base)"
expect "tree unchanged" test -z "$(git status --porcelain)"
expect "six or more criteria scored" test "$(grep -Ec '[0-9]+(\.[0-9]+)?/10|^\|[^|]+\| *[0-9]+(\.[0-9]+)? *\|' "$EVAL/out.txt")" -ge 7
expect "a total line" grep -Eiq '(Total|Итого)[^0-9]*[0-9]' "$EVAL/out.txt"
```
