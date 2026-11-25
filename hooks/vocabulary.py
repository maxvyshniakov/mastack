"""Shared command vocabulary for the Bash checks.

One definition of the base sets so checks do not drift silently. Checks that
intentionally narrow a base set (e.g. `git_guard` and `zsh_word_split` on
`WRAPPERS`) state their difference explicitly against these constants.
"""
from __future__ import annotations

import re

WRAPPERS = frozenset({"env", "command", "builtin", "nohup", "time", "sudo", "exec", "noglob", "nocorrect", "nice"})
GIT_OPTIONS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
                                    "--config-env"})
SIGNAL = re.compile(r"-(\d+|[A-Z][A-Z0-9+-]*|SIG[A-Za-z0-9+-]+)")
SHELLS = frozenset({"sh", "bash", "zsh"})
OWNER_TOOLS = frozenset({"spawnfather", "junkfather"})
LEASED_RUNNERS = {"slotfather": "run", "spawnfather": "own", "junkfather": "own"}
