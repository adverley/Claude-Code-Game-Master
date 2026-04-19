"""One-time sys.path setup so commands can import from lib/ and .claude/modules/ directly.

Imported from `discord_bot/__init__.py`, this module is idempotent: each path is
added at most once regardless of how many times this module is re-imported.
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

_EXTRA_PATHS = [
    _PROJECT_ROOT / "lib",
    _PROJECT_ROOT / ".claude" / "modules" / "inventory-system" / "lib",
    _PROJECT_ROOT / ".claude" / "modules" / "multi-character" / "lib",
]


def _install() -> None:
    for p in _EXTRA_PATHS:
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


_install()
