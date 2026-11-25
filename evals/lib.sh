# Helpers for scenario setup blocks. bin/eval sources this file with $EVAL set
# to the scenario's scratch directory.

# make_repo <branch> [more branches...]
# A bare origin and a clone at $EVAL/repo on <branch>, one start commit pushed
# to every named branch. Leaves the shell in $EVAL/repo.
make_repo() {
  mkdir -p "$EVAL/log" "$EVAL/state" &&
    git init -q --bare -b "$1" "$EVAL/origin.git" &&
    git init -q -b "$1" "$EVAL/repo" &&
    cd "$EVAL/repo" &&
    git config user.name Eval &&
    git config user.email eval@example.com &&
    git config commit.gpgsign false &&
    git config core.hooksPath .git/hooks &&
    git remote add origin "$EVAL/origin.git" &&
    printf '# Fixture\n' > README.md &&
    git add README.md &&
    git commit -qm "chore: start" &&
    for branch in "$@"; do git push -q origin "HEAD:refs/heads/$branch" || return 1; done &&
    git fetch -q origin &&
    git branch -q --set-upstream-to "origin/$1"
}

# commit_file <path> <content> <message>
commit_file() {
  mkdir -p "$(dirname "$1")" && printf '%s\n' "$2" > "$1" && git add "$1" && git commit -qm "$3"
}

# save <name> <value>: remember a value for the grade block as $(state <name>).
save() { printf '%s\n' "$2" > "$EVAL/state/$1"; }
state() { cat "$EVAL/state/$1"; }

# origin_rev <ref>
origin_rev() { git --git-dir="$EVAL/origin.git" rev-parse --verify -q "$1"; }

# install_pre_push: a pre-push hook that logs how each push was made (through
# the promote tool or bare) and runs ./check.sh when it exists.
install_pre_push() {
  cat > .git/hooks/pre-push <<HOOK
#!/usr/bin/env bash
EVAL='$EVAL'
HOOK
  cat >> .git/hooks/pre-push <<'HOOK'
while read -r local_ref local_sha remote_ref remote_sha; do
  echo "via=${EVAL_PROMOTE:-bare} $remote_ref $local_sha" >> "$EVAL/log/pushes.log"
done
[ -x ./check.sh ] && ./check.sh
exit 0
HOOK
  chmod +x .git/hooks/pre-push
}

# install_promote: tools/promote <sha> [--ship], a stand-in promote tool that
# logs its call, pushes the SHA and fast-forwards the checked-out branch.
install_promote() {
  mkdir -p tools &&
    printf '#!/usr/bin/env bash\nset -euo pipefail\nEVAL=%q\n' "$EVAL" > tools/promote &&
    cat >> tools/promote <<'TOOL'
echo "$*" >> "$EVAL/log/promote.log"
sha=$(git rev-parse --verify "$1^{commit}")
refs=("$sha:refs/heads/dev")
[[ ${2:-} == --ship ]] && refs+=("$sha:refs/heads/main")
EVAL_PROMOTE=promote git push --atomic origin "${refs[@]}"
[[ $(git branch --show-current) == dev ]] && git merge -q --ff-only "$sha"
echo "promoted $sha"
TOOL
  chmod +x tools/promote
}

# install_gate: ./check.sh, a gate that logs each run.
install_gate() {
  printf '#!/usr/bin/env bash\necho run >> %q\n' "$EVAL/log/check.log" > check.sh && chmod +x check.sh
}

# tool_uses [name]: one line per tool call of the agent, "<tool>\t<input as JSON>",
# optionally only calls of one tool. Claude runs only (reads $EVAL/agent.jsonl).
tool_uses() {
  [ -s "$EVAL/agent.jsonl" ] || return 0
  python3 - "$EVAL/agent.jsonl" "${1:-}" <<'PY'
import json, sys
path, only = sys.argv[1], sys.argv[2]
for line in open(path, encoding="utf-8"):
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue
    if event.get("type") != "assistant":
        continue
    for block in event.get("message", {}).get("content", []):
        if block.get("type") == "tool_use" and (not only or block.get("name") == only):
            print(f"{block['name']}\t{json.dumps(block.get('input', {}), ensure_ascii=False)}")
PY
}

# skill_loaded <name>: true when Claude's agent.jsonl records a Skill call for
# <name>; passes on harnesses that do not emit agent.jsonl (Codex, none).
skill_loaded() {
  [ -s "$EVAL/agent.jsonl" ] || return 0
  tool_uses Skill | grep -q "\"$1\""
}

# install_lane: tools/lane, a stand-in lane tool with Lanefather's command
# line. Every call lands in $EVAL/log/lane.log. `check <id>` refuses a dirty
# tree, runs ./check.sh and logs the tree it passed to $EVAL/log/receipts.log;
# `review <id>` prints $EVAL/state/findings-<id>; `list` prints
# $EVAL/state/lanes; `--help` anywhere prints a usage line. Other commands only
# log and answer ok.
install_lane() {
  mkdir -p tools &&
    printf '#!/usr/bin/env bash\nEVAL=%q\n' "$EVAL" > tools/lane &&
    cat >> tools/lane <<'TOOL'
echo "$*" >> "$EVAL/log/lane.log"
for arg in "$@"; do
  [[ $arg == -h || $arg == --help ]] && { echo "usage: tools/lane <command> [args] (Lanefather's command line)"; exit 0; }
done
cmd=${1:-}; shift
case $cmd in
  check)
    [[ -z $(git status --porcelain) ]] || { echo "check $1: refused, the worktree has uncommitted changes"; exit 1; }
    tree=$(git rev-parse 'HEAD^{tree}')
    if ./check.sh; then echo "$1 $tree green" >> "$EVAL/log/receipts.log"; echo "check $1: green, receipt for tree $tree"
    else echo "check $1: red"; exit 1; fi ;;
  list) cat "$EVAL/state/lanes" 2>/dev/null ;;
  review)
    case " $* " in
      *" --fix-lane "*) echo "registered $1-review-fixes on the worktree of $1" ;;
      *" --mark "*) echo "marked" ;;
      *) cat "$EVAL/state/findings-$1" 2>/dev/null || echo "review $1: none" ;;
    esac ;;
  start) echo "registered ${1:-?}" ;;
  *) echo "$cmd: ok" ;;
esac
TOOL
  chmod +x tools/lane
}
