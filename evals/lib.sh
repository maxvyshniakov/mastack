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
