# Changelog

## Unreleased

## 0.2.0

- Skills: `to-spec`, `roadmap`, `prototype`, `research`, `orchestrate` (with an
  implementer brief), `deps-update`, `rate`, `friction-audit`, `agent-docs`,
  `retro`, `reprompt` (user-invoked), `video-feedback` (with its transcription
  script and tests; artifacts default to the temp directory).
- `rate` scores each criterion as `<criterion>: <n>/10 - <gap>` and ends with
  `Total: <n>/10`.
- `bin/eval` records Claude's events in `agent.jsonl`; `tool_uses` in
  `evals/lib.sh` lists the tool calls for grade blocks. Scenarios for
  `deps-update` and `rate`.
- `bin/check` allows issue references under the placeholder owners `owner/`
  and `acme/`.
- README: install notes; `models.md` states the visual and two-lens rules as
  the author's preferences.

## 0.1.0

- Skills: `grill-me`, `critique`, `architecture`, `tdd`, `debug`,
  `cross-review`, `commit`, `push`, `release`, `finish`, `cleanup`, `status`,
  `handoff`.
- `CONTRACT.md`: the `docs/agents/*.md` files skills read from a project.
- `models.toml` and `models.md`: one table of roles, models and fallbacks.
- `bin/install` links skills into `~/.claude/skills` and `~/.agents/skills`.
- `bin/check` finds private details in the tree or the whole history.
- `bin/eval` with scenarios for `push` and `commit`.
