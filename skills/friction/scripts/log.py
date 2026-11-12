#!/usr/bin/env python3
"""Log the owner's correction to the friction journal: `/friction <text>` runs this. Passes its arguments on to
`bin/friction log` of the mastack checkout this skill is linked from."""
import os
import sys
from pathlib import Path

FRICTION = Path(__file__).resolve().parents[3] / "bin" / "friction"
if not FRICTION.is_file():
    sys.exit(f"friction: {FRICTION} is missing; /friction needs the mastack checkout, not a copied skill")
os.execv(sys.executable, [sys.executable, str(FRICTION), "log", *sys.argv[1:]])
