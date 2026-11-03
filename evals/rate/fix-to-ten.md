# Fix until 10/10, then a blind re-score

The user asks for a score and for the work to be brought to 10. The agent
scores against a rubric, improves the README, and has a fresh agent re-score
after the last edit rather than grading its own fixes.

## Prompt

```text
Оцени README.md из 10 и чини, пока не будет 10/10.
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
save readme "$(git hash-object README.md)"
```

## Grade

```sh grade
cd "$EVAL/repo"
expect "the rate skill was loaded" sh -c '. "$MASTACK/evals/lib.sh"; tool_uses Skill | grep -q "\"rate\""'
expect "README improved" test "$(git hash-object README.md)" != "$(state readme)"
expect "README documents both options" sh -c 'grep -q -- "--name" README.md && grep -q -- "--shout" README.md'
expect "a total line" grep -Eiq '(Total|Итого)[^0-9]*[0-9]' "$EVAL/out.txt"
expect "a subagent re-scored after the last README edit" sh -c '
  . "$MASTACK/evals/lib.sh"
  tool_uses | awk -F "\t" "
    /^(Edit|Write)\t/ && /README.md/ { last_edit = NR }
    /^(Agent|Task)\t/ { last_agent = NR }
    END { exit !(last_edit && last_agent > last_edit) }"'
```
