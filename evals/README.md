# Evals

Each scenario is one Markdown file: what it tests, the prompt, a setup block that
builds a scratch repository, and a grade block that checks what the agent left
behind. Grading looks at Git state and logs, not at the agent's prose, except
where the report itself is the requirement.

```sh
bin/eval --list
bin/eval push                      # every push scenario, with Claude (Opus)
bin/eval commit mixed-file --keep  # one scenario, keep the scratch directory
bin/eval push --agent codex        # the same scenarios with Codex (Sol)
```

The runner links every mastack skill into the scratch repository's
`.claude/skills` and `.agents/skills`, and runs Claude with project settings only,
so user-level hooks and skills do not decide the result. Permissions stay
narrow: Claude runs in auto mode with file tools, Git and the fixture's scripts
allowed up front and everything else judged by the auto-mode classifier; Codex
runs in its workspace-write sandbox limited to the scratch directory. The
runner never skips permission checks. Denied tool calls are printed under the
scenario, since an agent that hits one usually stops and asks. It prints `PASS` or
`FAIL` per assertion and keeps the scratch directory of a failed scenario
(`agent.log`, `out.txt`, `log/`, `repo/`).

## Writing a scenario

- One behavior per scenario, ideally one that once went wrong.
- Setup uses the helpers in [lib.sh](lib.sh): `make_repo`, `commit_file`,
  `save`/`state`, `origin_rev`, `install_promote`, `install_pre_push`,
  `install_gate`. The stand-in promote tool and pre-push hook log every call,
  so the grade can tell a promoted push from a bare one.
- Grade with `expect "<what>" <command>` and `refute "<what>" <command>`.
- For Claude runs, `$EVAL/agent.jsonl` holds every event and `tool_uses [tool]`
  prints one line per tool call (`<tool>\t<input JSON>`), so a grade can check
  what the agent did and in which order, such as a subagent after the last edit.
- A prompt that needs task history states it as context, since a headless run
  has no earlier conversation.
- Some prompts are in Russian on purpose: a skill must trigger from a request
  in the user's own language, while its description stays in English.

## When to run

After changing a skill the scenario covers, and when a new model becomes the
default. A model that passes without the skill installed marks a line the skill
no longer needs.
