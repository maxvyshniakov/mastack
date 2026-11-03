# Committing in a shared tree

A temporary index isolates your commit from someone else's staging. It does not
isolate working files, stop `HEAD` from moving, or make an old index safe to
put back after a commit.

1. Record the parent SHA, the real index's staged diff (`git diff --cached`), and
   the working and untracked paths you will touch. Keep recovery copies outside
   the repository.
2. Set `GIT_INDEX_FILE=<tmp>` on each command that builds the candidate; never
   export it. Initialise it with `GIT_INDEX_FILE=<tmp> git read-tree HEAD`.
3. Stage an allowlist. For a mixed file, build the intended content as parent +
   your hunks (`git apply --cached` of your hunks, or `git update-index
   --cacheinfo` with a blob from `git hash-object -w`). Adding the whole working
   file takes the other task's hunks with it.
4. When working files could hide a missing file or import, check out the
   candidate tree into a scratch worktree and run the checks there.
5. Recheck `HEAD` and the files you selected right before committing. If either
   changed, rebuild; never swap a validated tree for newer working content.
6. Commit with `GIT_INDEX_FILE=<tmp> git commit`. Then the real index is stale:
   entries for the files you committed now describe the old parent. Refresh just
   those paths (`git reset -q -- <your paths>` is safe only for paths nobody else
   staged); if someone staged overlapping hunks in the same file, keep the
   recovery copy and ask before touching it.
7. Compare the real index and working files with what you recorded in step 1.
   Delete only your temporary files.

Shortcuts that look harmless and are not, in a shared tree: whole-index
`git reset`, `git read-tree HEAD` on the real index, `git stash` / `pop`,
`git checkout -- <file>`, `git restore`. Each can erase someone's staging or
overwrite their edits. An empty `git diff --cached` afterwards is not proof that
their staged intent survived.
