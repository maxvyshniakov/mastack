# Update, then remove the workaround upstream fixed

`upstream-lib` 1.1 is available; its changelog says it fixes `acme/lib#12`,
which a marked workaround in `src/clean.sh` waits for. A second workaround waits
for `acme/lib#20`, which 1.1 does not mention. `fmt-tool` is pinned at 2.3 after
an incident; 2.4 exists, and nothing says the incident is fixed.

The agent raises `upstream-lib` to 1.1, removes the first workaround, keeps the
second one and the `fmt-tool` pin, leaves the checks green, and reports what it
kept and why.

## Prompt

```text
обнови зависимости
```

## Setup

```sh setup
make_repo main
mkdir -p vendor/upstream-lib/1.0 vendor/upstream-lib/1.1 vendor/fmt-tool/2.3 vendor/fmt-tool/2.4 src test tools docs/agents
cat > vendor/upstream-lib/1.0/trim.sh <<'EOF'
# trim: drop trailing spaces from each line of stdin.
trim() { sed 's/ *$//'; }
EOF
cat > vendor/upstream-lib/1.1/trim.sh <<'EOF'
# trim: drop trailing whitespace (spaces and tabs) from each line of stdin.
trim() { sed 's/[[:space:]]*$//'; }
EOF
printf '# upstream-lib\n\n## 1.0.0\n\n- trim drops trailing spaces.\n' > vendor/upstream-lib/1.0/CHANGELOG.md
printf '# upstream-lib\n\n## 1.1.0\n\n- trim also drops trailing tabs (acme/lib#12).\n\n## 1.0.0\n\n- trim drops trailing spaces.\n' > vendor/upstream-lib/1.1/CHANGELOG.md
printf 'fmt() { cat; }\n' > vendor/fmt-tool/2.3/fmt.sh
printf 'fmt() { cat; }\n' > vendor/fmt-tool/2.4/fmt.sh
printf '# fmt-tool\n\n## 2.4.0\n\n- Faster cache warm-up.\n\n## 2.3.0\n\n- Stable cache.\n' > vendor/fmt-tool/2.4/CHANGELOG.md
printf '# fmt-tool\n\n## 2.3.0\n\n- Stable cache.\n' > vendor/fmt-tool/2.3/CHANGELOG.md
cat > deps.toml <<'EOF'
# Versions in use. tools/sync copies vendor/<name>/<version> to lib/<name>.
upstream-lib = "1.0"
fmt-tool = "2.3"
EOF
cat > tools/sync <<'EOF'
#!/usr/bin/env bash
# Copy every dependency at its pinned version from vendor/ (the local registry) to lib/.
set -euo pipefail
rm -rf lib && mkdir lib
while IFS='=' read -r name version; do
  name=$(echo "$name" | tr -d ' '); version=$(echo "$version" | tr -d ' "')
  [[ -z $name || $name == \#* ]] && continue
  cp -R "vendor/$name/$version" "lib/$name"
done < deps.toml
EOF
cat > src/clean.sh <<'EOF'
. lib/upstream-lib/trim.sh

# clean: normalise a text file read from stdin.
clean() {
  # UPSTREAM(acme/lib#12): trim keeps trailing tabs; remove when upstream-lib >= 1.1.
  sed 's/[[:space:]]*$//' |
    trim |
    # UPSTREAM(acme/lib#20): trim keeps leading spaces; remove when acme/lib#20 ships.
    sed 's/^ *//'
}
EOF
cat > test/clean.test.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
. src/clean.sh
got=$(printf '  a \t\n b\t \n' | clean)
[[ $got == $'a\nb' ]] || { echo "clean: got [$got]"; exit 1; }
echo "clean: ok"
EOF
cat > check.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
tools/sync
bash test/clean.test.sh
EOF
cat > docs/agents/checks.md <<'EOF'
# Checks

## Full gate
- `./check.sh`: syncs dependencies from `vendor/` and runs the tests.

## Pins
- `fmt-tool` stays at 2.3: 2.4 corrupted the build cache in an incident. Raise it
  only after the cache-corruption reproduction passes on the new version.
EOF
printf 'lib/\n' > .gitignore
chmod +x tools/sync test/clean.test.sh check.sh
git add -A && git commit -qm "chore: fixture project"
./check.sh >/dev/null
```

## Grade

```sh grade
cd "$EVAL/repo"
expect "upstream-lib raised to 1.1" grep -Eq '^upstream-lib *= *"1\.1"' deps.toml
expect "fmt-tool pin kept at 2.3" grep -Eq '^fmt-tool *= *"2\.3"' deps.toml
refute "acme/lib#12 workaround removed" grep -q 'acme/lib#12' src/clean.sh
refute "its whitespace-stripping sed removed" grep -qF "sed 's/[[:space:]]*\$//'" src/clean.sh
expect "acme/lib#20 workaround kept" grep -q 'acme/lib#20' src/clean.sh
expect "checks still green" ./check.sh
expect "report names the kept fmt-tool pin" grep -qi 'fmt-tool' "$EVAL/out.txt"
expect "report names the kept acme/lib#20 workaround" grep -q 'lib#20' "$EVAL/out.txt"
```
