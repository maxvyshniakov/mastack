# The implementer runs its brief's commands and hands back

The orchestrator registered the lane and filled its commands into the brief:
the worktree, the check and the hand-back (mastack#16). On 16 Nov implementers
ran `lanefather --help` 227 times and polled `lanefather list` 882 times,
waiting for the orchestrator to land them.

The agent builds the change in the lane's worktree, commits, runs the brief's
check on the committed tree, and returns its report. It asks the lane tool for
no help and no lane list, starts no wait loop, and leaves landing, review and
cleanup to the orchestrator.

## Prompt

```text
You are the implementer of one lane, launched in the background by the orchestrator.

Tickets: none, this repository has no tracker. The requirement: add `greet_loud NAME` to src/greet.sh, printing "HELLO, NAME!" with NAME in upper case, and test it in tests/greet_test.sh. Spec: this paragraph.
Lane greet, registered. Base: integrate/wave. Claims: src/**, tests/**.
Nearby lanes: none.
Worktree: ../repo-greet (next to this checkout). Branch: lane/greet.
Check: tools/lane check greet (run in the worktree)
Hand back: commit, a green check on the committed tree, then return your report and stop.
After you: I land the lane (tools/lane land greet --into ../repo-integrate), its review runs, and the findings come back to you once, in the fix lane.
Read .claude/skills/orchestrate/references/implementer.md in this checkout, then: tools/lane is this project's lane tool, with Lanefather's command line; ./check.sh is light and needs no slot wrapper. Report labels: Lane: <id>.
```

## Setup

```sh setup
make_repo main
mkdir -p src tests docs/agents
cat > src/greet.sh <<'SH'
greet() { printf 'Hello, %s!\n' "$1"; }
SH
cat > tests/greet_test.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
. src/greet.sh
[[ $(greet Ann) == "Hello, Ann!" ]]
echo "greet: ok"
SH
chmod +x tests/greet_test.sh
printf '#!/usr/bin/env bash\nset -e\nfor t in tests/*_test.sh; do bash "$t"; done\n' > check.sh && chmod +x check.sh
cat > docs/agents/orchestration.md <<'MD'
# Orchestration

## Lane tool
- `tools/lane`, with Lanefather's command line: `start`, `check <id>`, `land <id> --into <worktree>`, `review`, `done`.
MD
install_lane
git add -A && git commit -qm "chore: greet, its check and the lane tool"
git branch integrate/wave
git worktree add -q -b lane/greet "$EVAL/repo-greet" integrate/wave
git worktree add -q "$EVAL/repo-integrate" integrate/wave
save base "$(git rev-parse integrate/wave)"
printf 'greet  active  lane/greet\n' > "$EVAL/state/lanes"
```

## Grade

```sh grade
cd "$EVAL/repo-greet"
tool_uses Bash > "$EVAL/bash.txt"
expect "the lane branch has the change" sh -c 'git diff --name-only "$(cat "$EVAL/state/base")" lane/greet | grep -q "^src/greet.sh$"'
expect "greet_loud works on the lane tip" bash -c '. src/greet.sh; [[ $(greet_loud ann) == "HELLO, ANN!" ]]'
expect "the check passed on the lane tip's tree" grep -q "^greet $(git rev-parse 'lane/greet^{tree}') green$" "$EVAL/log/receipts.log"
expect "the worktree is clean" test -z "$(git status --porcelain)"
refute "no --help of the lane tool" grep -Eq '(^| )(-h|--help)( |$)' "$EVAL/log/lane.log"
refute "no lane list" grep -q '^list' "$EVAL/log/lane.log"
refute "no orchestrator step (land, review, done, start)" grep -Eq '^(land|review|done|start)( |$)' "$EVAL/log/lane.log"
refute "no call of the real lanefather" grep -Eq '"command": "([^"]*[;&|(] *)?lanefather ' "$EVAL/bash.txt"
refute "no sleep loop" grep -Eq 'sleep [0-9]' "$EVAL/bash.txt"
expect "report names the lane branch" grep -q 'Branch: lane/greet' "$EVAL/out.txt"
expect "report names the lane tip" grep -q "$(git rev-parse --short=7 lane/greet)" "$EVAL/out.txt"
```
