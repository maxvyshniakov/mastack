"""Prepare a tagged child of published dev, without executing files from dev."""
import json
import os
import re
import subprocess
import sys


def git(*args, data=None):
    return subprocess.check_output(["git", *args], input=data, text=True).strip()


source, version = os.environ["SOURCE"], os.environ["VERSION"]
number = r"(?:0|[1-9][0-9]*)"
if not re.fullmatch("[0-9a-f]{40}", source) or not re.fullmatch(fr"{number}\.{number}\.{number}", version):
    sys.exit("Invalid commit or version")
dev = git("rev-parse", "origin/dev")
main = git("rev-parse", "origin/main")
if git("rev-parse", "HEAD") != main:
    sys.exit("The release workflow is stale")
tag = f"refs/tags/v{version}"
if git("tag", "--list", f"v{version}"):
    if (git("cat-file", "-t", tag) == "tag" and git("rev-parse", f"{tag}^{{commit}}") == main == dev
            and source in (main, git("rev-parse", f"{main}^"))):
        print("Release already published; verifying remote refs.")
        sys.exit(0)
    sys.exit("Version already exists on a different release")
if source != dev:
    sys.exit("The source or release workflow is stale")
git("merge-base", "--is-ancestor", "origin/main", source)
runs = json.loads(subprocess.check_output([
    "gh", "run", "list", "--workflow", "check.yml", "--event", "push", "--branch", "dev",
    "--commit", source, "--limit", "1", "--json", "conclusion",
]))
if not runs or runs[0]["conclusion"] != "success":
    sys.exit("The dev push must pass CI before promotion")

notes = subprocess.check_output(["git", "show", f"{source}:CHANGELOG.md"]).decode()
pending = re.search(r"^## Unreleased\n(.*?)(?=^## (\d+\.\d+\.\d+)$)", notes, re.M | re.S)
if not pending or not pending[1].strip():
    sys.exit("No Unreleased notes to promote")
if tuple(map(int, version.split("."))) <= tuple(map(int, pending[2].split("."))):
    sys.exit("Version must be newer than the latest release")

updated = notes[:pending.start(1)] + f"\n## {version}\n" + notes[pending.start(1):]
git("read-tree", source)
blob = git("hash-object", "-w", "--stdin", data=updated)
git("update-index", "--cacheinfo", f"100644,{blob},CHANGELOG.md")
git("config", "user.name", "Mastack Promote")
git("config", "user.email", "mastack-promote@users.noreply.github.com")  # check:allow
release = git("commit-tree", git("write-tree"), "-p", source, "-m", f"chore: release {version}")
git("tag", "-a", f"v{version}", release, "-m", f"Mastack {version}")
