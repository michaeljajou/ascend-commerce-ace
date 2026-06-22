"""Pytest bootstrap: make the shared `_lib` importable from anywhere in the suite.

Skill scripts add `skills` to sys.path at runtime; we mirror that here so tests can
`from _lib import ...` and import skill scripts by their `scripts/` directory.
"""

import sys
from pathlib import Path

ACE = Path(__file__).resolve().parent / "skills"
if str(ACE) not in sys.path:
    sys.path.insert(0, str(ACE))
