---
name: friction
description: "Log the owner's correction of how an agent used a package to the friction journal (/friction <text>)."
disable-model-invocation: true
---

# /friction

The owner corrects how an agent used one of their packages. Record it as one
event in the local friction journal, so a later friction audit counts it.

1. Run, with the owner's text as given (quote it for the shell):

   ```sh
   python3 <this skill's directory>/scripts/log.py [--package <npm name>] [--component <export>] "<text>"
   ```

   Pass `--package` and `--component` only when the text or the work just
   discussed names them (`@scope/ui-kit`, `ItemBody`); never guess. Without
   them the script takes what the text names. The session and project come
   from the environment and the current directory.
2. Reply with the one line it prints. Do not act on the correction unless the
   owner asked for that too; then apply it as usual.

Nothing leaves the machine. `repo-kit friction report` ranks the journal.
