# Third-party notices

mastack's own code and text are under the MIT license in [LICENSE](LICENSE).
This file records what the pack owes to others: work it adapts, and tools it
runs but does not ship.

## Adapted: Matt Pocock's skills

- Source: <https://github.com/mattpocock/skills>
- License: MIT, Copyright (c) 2026 Matt Pocock (full text below).
- What was taken: ideas, process and structure. The texts in this repository
  are rewritten, not copied; no file from that repository is included.
- Skills that build on it, with the upstream skill they draw on:

  | mastack skill | Upstream skill |
  |---|---|
  | `grill-me` | `grill-me`, `grilling` |
  | `roadmap` | `wayfinder` |
  | `prototype` | `prototype` |
  | `research` | `research` |
  | `to-spec` | `to-spec`, `to-tickets` |
  | `orchestrate` | `implement-spec` |
  | `architecture` | `codebase-design`, `improve-codebase-architecture` |
  | `tdd` | `tdd` |
  | `debug` | `diagnosing-bugs` |
  | `cross-review` | `code-review` |
  | `agent-docs` | `writing-for-agents` |
  | `retro` | `retro` |

- Redistribution: allowed. MIT asks that the notice travel with "all copies or
  substantial portions"; the rewrite shares little text, and the notice is
  kept anyway, so attribution survives any copy of this repository.

```
MIT License

Copyright (c) 2026 Matt Pocock

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Run, not shipped

The pack calls these programs when they are installed. None of them is
included in this repository; each keeps its own license, which you accept
when you install it.

| Tool | Used by | Notes |
|---|---|---|
| [Claude Code](https://code.claude.com/docs), [Codex CLI](https://github.com/openai/codex) | every skill, `bin/eval` | The agents the pack is written for |
| [GitHub CLI](https://cli.github.com) (`gh`) | `push`, `status`, `orchestrate`, others | Tracker and CI access |
| [Slotfather](https://github.com/maxvyshniakov/slotfather) | `lease_guard`, `orchestrate` | Optional machine-slot queue |
| Lanefather | `unguarded_sequence`, `orchestrate`, `status` | Optional lane tool, by the same author; recognised by name only |
| [FFmpeg](https://ffmpeg.org/legal.html), [OpenAI Whisper](https://github.com/openai/whisper) or [mlx-whisper](https://github.com/ml-explore/mlx-examples) | `video-feedback` | `mlx_whisper` downloads the `mlx-community/whisper-large-v3-mlx` weights on first use |
| [Playwright](https://playwright.dev), Safari Technology Preview and `safaridriver` | `browser-verify` | Browser engines for screenshots |

Two links in [CONTRACT.md](CONTRACT.md) cite the Claude Code and Codex
documentation for how skills with the same name resolve; nothing is quoted
from them beyond a section title.
