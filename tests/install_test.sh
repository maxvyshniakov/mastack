#!/usr/bin/env bash
# Tests for bin/install: skill selection, uninstall, dry runs and shadowing.
# Runs against scratch targets and projects; never touches the real skill dirs.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd -P)
scratch=$(cd "$(mktemp -d)" && pwd -P)
trap 'rm -rf "$scratch"' EXIT
export MASTACK_CONFIG=$scratch/config MASTACK_SCAN_ROOT=$scratch/home
mkdir -p "$MASTACK_CONFIG" "$MASTACK_SCAN_ROOT"

failures=0
check() {
  local label=$1; shift
  if "$@"; then echo "ok    $label"; else echo "FAIL  $label"; failures=$((failures + 1)); fi
}

t=$scratch/target
install() { "$root/bin/install" --target "$t" "$@" > "$scratch/out" 2>&1; }
linked() { [[ -L $t/$1 && $(readlink "$t/$1") == "$root/skills/$1" ]]; }
absent() { [[ ! -e $t/$1 && ! -L $t/$1 ]]; }
said() { grep -qF -- "$1" "$scratch/out"; }
fresh() { rm -rf "$t" "$scratch/p"; mkdir -p "$t"; }
count() { find "$t" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' '; }
total=$(find "$root/skills" -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l | tr -d ' ')

fresh
check "--only installs exactly the named skills" sh -c "
  '$root/bin/install' --target '$t' --only rate,debug >/dev/null 2>&1 &&
  [ \$(find '$t' -mindepth 1 -maxdepth 1 | wc -l) -eq 2 ]"
check "--only links rate" linked rate

fresh
install --skip push,release,finish
check "--skip installs the rest" test "$(count)" -eq $((total - 3))
check "--skip leaves push out" absent push
check "--skip still links commit" linked commit

fresh
check "an unknown name exits 2" sh -c "'$root/bin/install' --target '$t' --only nope >/dev/null 2>&1; [ \$? -eq 2 ]"
check "an unknown name changes nothing" test "$(count)" -eq 0

fresh
install --dry-run --only rate
check "--dry-run says what it would link" said "link   rate"
check "--dry-run says it is a dry run" said "dry run: nothing below is changed"
check "--dry-run links nothing" test "$(count)" -eq 0
check "--dry-run honors --only" sh -c "! grep -q 'skills/debug' '$scratch/out'"

fresh
install --only rate,debug,tdd
install --uninstall --only debug
check "--uninstall --only removes the named skill" absent debug
check "--uninstall --only keeps the others" linked rate
install --uninstall --skip tdd
check "--uninstall --skip removes the unskipped" absent rate
check "--uninstall --skip keeps the skipped" linked tdd
install --uninstall --dry-run
check "--uninstall --dry-run removes nothing" linked tdd

fresh
mkdir -p "$t/rate"
install --only rate || true
check "a foreign directory is left alone" test -d "$t/rate" -a ! -L "$t/rate"
check "a foreign directory is reported" said "exists and is not ours"

fresh
p=$scratch/p
mkdir -p "$p/.claude/skills/push" "$p/.agents/skills/ship" "$p/docs/agents"
printf -- '---\nname: push\n---\n' > "$p/.claude/skills/push/SKILL.md"
printf -- '---\nname: "release"\ndescription: x\n---\n' > "$p/.agents/skills/ship/SKILL.md"
check "a shadowing skill exits 1" sh -c "'$root/bin/install' --target '$t' --project '$p' --only push,rate >'$scratch/out' 2>&1; [ \$? -eq 1 ]"
check "the shadow is reported with its path" said "shadow push: $p/.claude/skills/push"
check "the shadowing skill is held back" absent push
check "the other skill is installed" linked rate
install --project "$p" --only release || true
check "a frontmatter name shadows too" said "shadow release: $p/.agents/skills/ship"
touch "$p/docs/agents/publishing.md"
install --project "$p" --only push || true
check "publishing.md is noted" said "(project has docs/agents/publishing.md)"
install --project "$p" --only push --skip push
check "a skipped skill is not checked for shadowing" sh -c "! grep -q 'shadow push' '$scratch/out'"
install --project "$p" --only push --force
check "--force installs a shadowing skill" linked push

fresh
printf '# projects\n%s  # a comment\n' "$p" > "$MASTACK_CONFIG/projects"
mkdir -p "$p/.claude/skills/push"
install --only push || true
check "projects come from the config file" said "shadow push: $p/.claude/skills/push"
check "config shadows are held back" absent push
rm "$MASTACK_CONFIG/projects"
HOME=$scratch install --project "$p" --only push || true
check "paths under HOME are shown with ~" said "shadow push: ~/p/.claude/skills/push"

fresh
h=$MASTACK_SCAN_ROOT
git init -q "$h/app"
mkdir -p "$h/app/.claude/skills/push" "$h/notes/.claude/skills/tdd"
git -C "$h/app" -c user.name=t -c user.email=t@example.com commit -q --allow-empty -m init
git -C "$h/app" worktree add -q "$h/app-wt-1" 2>/dev/null
mkdir -p "$h/app-wt-1/.agents/skills/push"
install --only push,tdd || true
check "a repository under the scan root is checked" said "shadow push: $h/app/.claude/skills/push"
check "a worktree is marked as a copy" said "shadow push: $h/app-wt-1/.agents/skills/push (copy: worktree of $h/app)"
check "a folder that is not a repository is not scanned" sh -c "! grep -q 'shadow tdd' '$scratch/out'"
install --only tdd --project "$h/notes" || true
check "--project adds a folder outside the scan" said "shadow tdd: $h/notes/.claude/skills/tdd"

if ((failures)); then
  echo "install_test: $failures failure(s)" >&2
  exit 1
fi
echo "install_test: all passed"
