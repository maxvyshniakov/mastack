#!/usr/bin/env bash
# Tests for bin/install: skill selection, uninstall, dry runs and shadowing.
# Runs against scratch targets and projects; never touches the real skill dirs.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd -P)
scratch=$(cd "$(mktemp -d)" && pwd -P)
trap 'rm -rf "$scratch"' EXIT
export MASTACK_CONFIG=$scratch/config MASTACK_SCAN_ROOT=$scratch/home
export MASTACK_CLAUDE_SETTINGS=$scratch/settings.json  # never the real settings
export MASTACK_HOOKS_FROM_WORKTREE=1  # the tests may run in a worktree
mkdir -p "$MASTACK_CONFIG" "$MASTACK_SCAN_ROOT"
echo '{}' > "$MASTACK_CONFIG/hooks.json"

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
printf '# frozen\n%s\n' "$h/app" > "$MASTACK_CONFIG/ignore"
check "an ignored repository does not hold a skill back" install --only push
check "an ignored repository is not reported" sh -c "! grep -q 'app/.claude' '$scratch/out'"
check "a worktree of an ignored repository is skipped too" sh -c "! grep -q 'app-wt-1' '$scratch/out'"
git init -q "$h/other"
mkdir -p "$h/other/.claude/skills/push"
install --only push || true
check "a repository not in the ignore list is still checked" said "shadow push: $h/other/.claude/skills/push"
rm "$MASTACK_CONFIG/ignore"

# The Bash hook in the Claude Code settings.
sf=$MASTACK_CLAUDE_SETTINGS
cat > "$sf" <<'EOF'
{
  "permissions": {"allow": ["Bash(make:*)"]},
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash ~/.claude/hooks/macos-shell-pitfalls.sh", "timeout": 5}]},
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 /opt/app/tools/agent-hooks/zsh-word-split.py", "timeout": 5}]},
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 /opt/app/tools/agent-hooks/git-guard.py", "timeout": 5},
                                    {"type": "command", "command": "python3 /opt/other/audit.py", "timeout": 5}]},
      {"matcher": "Edit", "hooks": [{"type": "command", "command": "python3 /opt/app/tools/agent-hooks/unguarded-sequence.py"}]},
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/bash_guard.py", "timeout": 5}]},
      {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "python3 /opt/tools/hooks/bash_guard.py"}]},
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 /opt/app/tools/agent-hooks/lease-guard.py", "timeout": 10}]}
    ],
    "SubagentStop": [{"hooks": [{"type": "command", "command": "python3 /opt/app/tools/agent-hooks/lane-stop.py"}]}]
  }
}
EOF
cp "$sf" "$scratch/settings.orig"
rm -f "$scratch"/settings.json.mastack-backup-* "$MASTACK_CONFIG/hooks-installed.json"  # from the cases above
py() { python3 -c "import json, sys; s = json.load(open(sys.argv[1])); sys.exit(0 if ($1) else 1)" "$sf"; }
commands="[h['command'] for g in s['hooks']['PreToolUse'] for h in g['hooks']]"
bash_commands="[h['command'] for g in s['hooks']['PreToolUse'] if g.get('matcher') == 'Bash' for h in g['hooks']]"
ours="[c for c in $commands if c.endswith('$root/hooks/bash_guard.py')]"
backups() { find "$scratch" -maxdepth 1 -name 'settings.json.mastack-backup-*' | wc -l | tr -d ' '; }

fresh
install --dry-run || true  # earlier cases leave shadowed skills
check "hooks --dry-run changes nothing" cmp -s "$sf" "$scratch/settings.orig"
check "hooks --dry-run shows the new entry" grep -qE "^\+ +\"command\": \"sh -c .*$root/hooks/bash_guard.py\"" "$scratch/out"
check "hooks --dry-run shows a replaced entry" grep -qE "^-.*agent-hooks/git-guard.py" "$scratch/out"
install --only rate
check "--only without hooks leaves the settings alone" cmp -s "$sf" "$scratch/settings.orig"
install --skip hooks || true
check "--skip hooks leaves the settings alone" cmp -s "$sf" "$scratch/settings.orig"
install --only hooks
check "install says what it replaced" said "remove PreToolUse Bash: bash ~/.claude/hooks/macos-shell-pitfalls.sh"
check "install registers one dispatcher" py "len($ours) == 1"
check "it runs for Bash with a timeout" py "any(g['matcher'] == 'Bash' and g['hooks'][0].get('timeout') == 10 for g in s['hooks']['PreToolUse'] if g['hooks'][0]['command'] in $ours)"
check "the replaced Bash checks are gone" py "not any('agent-hooks/' in c or 'pitfalls' in c for c in $bash_commands)"
check "an Edit group naming an old check is left alone" py "'python3 /opt/app/tools/agent-hooks/unguarded-sequence.py' in $commands"
check "someone else's bash_guard.py is left alone" py "'python3 ~/.claude/hooks/bash_guard.py' in $commands and 'python3 /opt/tools/hooks/bash_guard.py' in $commands"
check "a foreign handler in a replaced group stays" py "'python3 /opt/other/audit.py' in $commands"
check "other events and settings stay" py "s['hooks']['SubagentStop'][0]['hooks'][0]['command'].endswith('lane-stop.py') and s['permissions']['allow'] == ['Bash(make:*)']"
check "a backup of the original is written" sh -c "[ $(backups) -eq 1 ] && cmp -s '$scratch/settings.orig' \"\$(ls '$scratch'/settings.json.mastack-backup-*)\""
check "the installed command is recorded" grep -q bash_guard "$MASTACK_CONFIG/hooks-installed.json"
registered=$(python3 -c "import json, sys; s = json.load(open(sys.argv[1])); print(next(c for c in $commands if c.endswith('bash_guard.py') and c.startswith('sh ')))" "$sf")
hook() { printf '%s' '{"tool_input": {"command": "git stash"}}' | sh -c "$1"; }
denies() { hook "$1" | grep -q '"deny"'; }
passes() { local out; out=$(hook "$1") && [ -z "$out" ]; }
check "the registered command runs the checks" denies "$registered"
check "a removed checkout lets every command through" passes "${registered%"$root/hooks/bash_guard.py"}$scratch/gone/bash_guard.py"
cp "$sf" "$scratch/settings.installed"
install --only hooks
check "a second install is a no-op" cmp -s "$sf" "$scratch/settings.installed"
check "a second install says ok" said "ok     hooks"
check "a second install writes no backup" test "$(backups)" -eq 1
install --uninstall --only push
check "uninstalling a skill keeps the hook" cmp -s "$sf" "$scratch/settings.installed"
mv "$MASTACK_CONFIG/hooks.json" "$scratch/hooks.json.aside"
install --uninstall --only hooks
check "uninstall removes mastack's entry" py "not $ours"
check "uninstall keeps every other entry" py "'python3 /opt/other/audit.py' in $commands and 'python3 ~/.claude/hooks/bash_guard.py' in $commands and 'SubagentStop' in s['hooks']"
cp "$sf" "$scratch/settings.uninstalled"
check "install refuses without the machine settings" sh -c "! '$root/bin/install' --target '$t' --only hooks >'$scratch/out' 2>&1"
check "the refusal says what to do" said "hooks.example.json"
check "a refused install changes nothing" cmp -s "$sf" "$scratch/settings.uninstalled"
mv "$scratch/hooks.json.aside" "$MASTACK_CONFIG/hooks.json"
fake=$scratch/worktree-checkout
mkdir -p "$fake/hooks" && cp "$root/hooks/register.py" "$fake/hooks/" && echo "gitdir: /elsewhere" > "$fake/.git"
check "a linked worktree is refused" sh -c "! python3 '$fake/hooks/register.py' --settings '$sf' --config '$MASTACK_CONFIG' >'$scratch/out' 2>&1"
check "the worktree refusal names the main checkout" said "install from the main checkout"
check "a refused worktree changes nothing" cmp -s "$sf" "$scratch/settings.uninstalled"
rm -f "$sf" "$scratch"/settings.json.mastack-backup-*
install --only hooks
check "a missing settings file is created" py "$commands == $ours and len($ours) == 1"
printf '{"hooks": ' > "$sf"
check "an unreadable settings file is refused" sh -c "! '$root/bin/install' --target '$t' --only hooks >'$scratch/out' 2>&1"
check "an unreadable settings file is left alone" test "$(cat "$sf")" = '{"hooks": '
printf '{"hooks": []}\n' > "$sf"
check "malformed hooks are refused" sh -c "! '$root/bin/install' --target '$t' --only hooks >'$scratch/out' 2>&1"
check "the refusal names the problem" said "is not an object"
check "malformed hooks are left alone" test "$(cat "$sf")" = '{"hooks": []}'
mkdir -p "$scratch/dotfiles" && echo '{}' > "$scratch/dotfiles/settings.json" && rm -f "$sf" && ln -s "$scratch/dotfiles/settings.json" "$sf"
install --only hooks
check "a symlinked settings file stays a symlink" test -L "$sf"
check "its target gets the hook" grep -q bash_guard "$scratch/dotfiles/settings.json"
rm -f "$sf"
check "--settings names another file" sh -c "'$root/bin/install' --target '$t' --only hooks --settings '$scratch/other.json' >/dev/null && grep -q bash_guard '$scratch/other.json'"

if ((failures)); then
  echo "install_test: $failures failure(s)" >&2
  exit 1
fi
echo "install_test: all passed"
