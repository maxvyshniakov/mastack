# A fix round starts through the fix-round path

Two landed lanes have review findings. On 13-16 Nov orchestrators batched such
findings into fix lanes started with a plain `start review-fixes-rN`; the lane
tool reviewed each as an ordinary lane at land, and the rounds chained six and
seven deep (mastack#17, fathers#174).

The agent registers the fix round through the lane tool's fix-round path,
`review <id> --fix-lane` per lane or one `start <fix-id> --fix-of alpha,beta`,
and never with a plain `start`.

## Prompt

```text
Orchestrating batch wave in this repository. Lanes alpha and beta have landed in integrate/wave and their reviews are back: `tools/lane review alpha` and `tools/lane review beta` print the findings. Register the fix round for these findings with the lane tool, then stop and tell me what you registered: I launch the implementer myself.
```

## Setup

```sh setup
make_repo main
mkdir -p src docs/agents
printf 'a=1\n' > src/alpha.sh && printf 'b=1\n' > src/beta.sh
cat > docs/agents/orchestration.md <<'MD'
# Orchestration

## Lane tool
- `tools/lane`, with Lanefather's command line, including `start <id> --fix-of A,B` (fathers#174).

## Review
- Every landed lane is reviewed once at land; findings are marked with `tools/lane review <id> --mark N fixed:<merge>|rejected:<reason>`.
MD
install_lane
git add -A && git commit -qm "chore: alpha, beta and the lane tool"
git branch integrate/wave
cat > "$EVAL/state/lanes" <<'TXT'
alpha  landed  review: 2 findings unmarked
beta   landed  review: 1 finding unmarked
TXT
cat > "$EVAL/state/findings-alpha" <<'TXT'
review alpha (sol): 2 findings
  1. P2 src/alpha.sh:1 `a` is never read; name it for what it counts or drop it.
  2. P3 src/alpha.sh:1 no test covers the default value.
TXT
cat > "$EVAL/state/findings-beta" <<'TXT'
review beta (sol): 1 finding
  1. P2 src/beta.sh:1 duplicates alpha's default; read it from one place.
TXT
```

## Grade

```sh grade
cd "$EVAL/repo"
covered() {
  grep '^review ' "$EVAL/log/lane.log" | grep -- '--fix-lane' | grep -Eq " $1( |$)" ||
    grep -Eq "^start .*--fix-of[ =]([^ ]*,)?$1(,| |$)" "$EVAL/log/lane.log"
}
expect "alpha's findings go to a fix round through the fix-round path" covered alpha
expect "beta's findings go to a fix round through the fix-round path" covered beta
refute "no plain start" sh -c 'grep "^start" "$EVAL/log/lane.log" | grep -vq -- "--fix-of"'
```
