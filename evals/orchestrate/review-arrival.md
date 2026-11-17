# Triage a finished review before the next land

A finished review used to wait until the batch gate, by which time later lanes
had rewritten its diff (mastack#11). The next coordinator action processes it.

## Prompt

```text
Continue orchestrating this batch. Alpha has landed and its review has just finished; beta is green and ready to land. Inspect the current lane state, perform the next coordination action, then stop so I can inspect it. Do not implement code in this turn.
```

## Setup

```sh setup
make_repo main
mkdir -p src docs/agents
printf 'a=1\n' > src/alpha.sh
cat > docs/agents/orchestration.md <<'MD'
# Orchestration
The lane tool is `tools/lane`, with Lanefather's command line. Integrate into
`integrate/wave`. A fix round uses `tools/lane review ID --fix-lane`.
MD
install_lane
git add -A && git commit -qm "batch fixture"
git branch integrate/wave
cat > "$EVAL/state/lanes" <<'TXT'
alpha  landed  review: 1 finding unmarked
beta   active  check: green
TXT
cat > "$EVAL/state/findings-alpha" <<'TXT'
review alpha (sol): 1 finding
  1. P2 src/alpha.sh:1 `a` is never read; name it for what it counts or drop it.
TXT
```

## Grade

```sh grade
expect "finished review enters its fix round" grep -Eq '^review alpha --fix-lane|^start .*--fix-of[ =]alpha' "$EVAL/log/lane.log"
refute "next lane does not land ahead of triage" grep -Eq '^land beta' "$EVAL/log/lane.log"
```
