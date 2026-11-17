# Prefer the canonical no-activation Safari route

## Prompt

```text
Use browser-verify to inspect the supplied launcher sources and write PLAN.md naming
which route can verify real Safari without taking focus, which route cannot, and
what acceptance is still needed for a replacement. This is source inspection only:
do not run either launcher or start any browser. The fixture is complete.
```

## Setup

```sh setup
make_repo main
mkdir -p docs/agents scripts
cat > docs/agents/checks.md <<'DOC'
# Browser and visual
For real STP use scripts/background.mjs. screenshots.mjs is an older tool.
DOC
cat > scripts/background.mjs <<'JS'
// Existing canonical real-STP check: exclusive lock, tokenized page bridge,
// open -g -b STP, AX placement with no raise, PID events, frontmost abort watcher.
throw new Error('Fixture source only; do not execute');
JS
cat > scripts/screenshots.mjs <<'JS'
// Older screenshotter: safaridriver POST /session, then activate(previous).
throw new Error('Fixture source only; do not execute');
JS
```

## Grade

```sh grade
cd "$EVAL/repo"
expect "chooses canonical route" grep -q 'background.mjs' PLAN.md
expect "identifies old foreground route" grep -q 'screenshots.mjs' PLAN.md
expect "does not equate handback with no focus" grep -Eiq 'handback|hand.*back|return.*focus|restore.*focus' PLAN.md
expect "requires native acceptance" grep -Eiq 'native|runtime' PLAN.md
```
